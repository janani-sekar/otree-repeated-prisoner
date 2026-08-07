"""
IRL-SG model from Fudenberg & Rehbinder (2024), Appendix D.

6 parameters: (alpha, beta, lam, p_CC, p_CD_DC, p_DD)

Initial round of supergame s for player i:
    p_initial_i(s) = sigmoid(alpha + beta * Delta_RD + e_i(s))

    where e_i(1) = 0 and experience updates after each supergame:
        e_i(s+1) = lam * a_i(s) * V_i(s) + e_i(s)

    a_i(s) = +1 if player cooperated in initial round, -1 if defected
    V_i(s) = total payoff in supergame s

Non-initial rounds: fixed memory-1 probabilities (semi-grim)
    After CC: p_CC
    After CD or DC: p_CD_DC
    After DD: p_DD

Parameters estimated via MLE (minimizing log-loss) on training data.

Data: experimental_data.csv with columns (id, session, inter, c, opp_c, payoff, delta, g, l).
Each row = one individual in one supergame; `inter` orders supergames within a session.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import roc_auc_score


PAPER_DEFAULTS = dict(alpha=-0.268, beta=1.291, lam=0.182, p_CC=0.995, p_CD_DC=0.355, p_DD=0.012)


def load_and_sort(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.sort_values(["session", "id", "inter"]).reset_index(drop=True)
    df["Delta_RD"] = df["delta"] - (df["g"] + df["l"]) / (1 + df["g"] + df["l"])
    return df


def preprocess(df: pd.DataFrame) -> dict:
    """Parse JSON once, build flat round-level arrays for fast prediction."""
    round_action = []
    round_prev_joint = []  # 0=CC, 1=CD, 2=DC, 3=DD, -1=initial
    round_delta_rd = []
    round_individual = []
    round_sg_idx = []

    sg_individual = []
    sg_delta_rd = []
    sg_initial_action = []  # +1 or -1
    sg_total_payoff = []
    sg_order = []

    individual_map = {}
    ind_counter = 0

    for _, row in df.iterrows():
        sess, pid = row["session"], row["id"]
        key = (sess, pid)
        if key not in individual_map:
            individual_map[key] = ind_counter
            ind_counter += 1
        ind_id = individual_map[key]

        actions = json.loads(row["c"])
        opp_actions = json.loads(row["opp_c"])
        payoffs = json.loads(row["payoff"])
        delta_rd = row["Delta_RD"]
        inter = row["inter"]

        for t in range(len(actions)):
            a = 1 if actions[t] == 1 else 0
            round_action.append(a)
            round_individual.append(ind_id)
            round_sg_idx.append(len(sg_individual))
            round_delta_rd.append(delta_rd)

            if t == 0:
                round_prev_joint.append(-1)
            else:
                pm = 1 if actions[t - 1] == 1 else 0
                po = 1 if opp_actions[t - 1] == 1 else 0
                round_prev_joint.append(pm * 2 + po)  # CC=3, CD=2, DC=1, DD=0

        sg_individual.append(ind_id)
        sg_delta_rd.append(delta_rd)
        sg_initial_action.append(1.0 if actions[0] == 1 else -1.0)
        sg_total_payoff.append(sum(payoffs))
        sg_order.append(inter)

    return {
        "round_action": np.array(round_action, dtype=np.float64),
        "round_prev_joint": np.array(round_prev_joint, dtype=np.int8),
        "round_delta_rd": np.array(round_delta_rd, dtype=np.float64),
        "round_individual": np.array(round_individual, dtype=np.int32),
        "round_sg_idx": np.array(round_sg_idx, dtype=np.int32),
        "sg_individual": np.array(sg_individual, dtype=np.int32),
        "sg_delta_rd": np.array(sg_delta_rd, dtype=np.float64),
        "sg_initial_action": np.array(sg_initial_action, dtype=np.float64),
        "sg_total_payoff": np.array(sg_total_payoff, dtype=np.float64),
        "sg_order": np.array(sg_order, dtype=np.int32),
        "n_individuals": ind_counter,
    }


def predict_probs(data: dict, alpha: float, beta: float, lam: float,
                  p_CC: float, p_CD_DC: float, p_DD: float) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized prediction. Returns (predicted_probs, actual_actions)."""
    prev = data["round_prev_joint"]
    n = len(prev)
    probs = np.empty(n, dtype=np.float64)

    # Non-initial rounds: vectorized memory-1 lookup
    # prev encoding: CC=3, CD=2, DC=1, DD=0, initial=-1
    is_initial = prev == -1
    probs[prev == 3] = p_CC
    probs[prev == 0] = p_DD
    probs[(prev == 1) | (prev == 2)] = p_CD_DC

    # Initial rounds: need sequential e_i per individual
    sg_ind = data["sg_individual"]
    sg_drd = data["sg_delta_rd"]
    sg_init_a = data["sg_initial_action"]
    sg_pay = data["sg_total_payoff"]
    sg_ord = data["sg_order"]

    e_i = np.zeros(data["n_individuals"], dtype=np.float64)

    sorted_sg = np.argsort(sg_ord, kind="stable")
    ind_prev = -1
    for sg in sorted_sg:
        ind = sg_ind[sg]
        if ind != ind_prev:
            ind_prev = ind
        probs_val = expit(alpha + beta * sg_drd[sg] + e_i[ind])
        e_i[ind] += lam * sg_init_a[sg] * sg_pay[sg]

        # Not used directly — we need to assign to the right round-level slots
        # but we stored sg_idx per round, so we'll do a second pass below

    # Recompute initial probs properly: we need e_i at each supergame
    # Reset and compute e_i per supergame, storing the value at each SG
    e_i[:] = 0.0
    sg_e = np.empty(len(sg_ind), dtype=np.float64)

    # Group supergames by individual, process in order
    ind_sg_start = np.zeros(data["n_individuals"] + 1, dtype=np.int32)
    for i in sg_ind:
        ind_sg_start[i + 1] += 1
    np.cumsum(ind_sg_start, out=ind_sg_start)

    # Supergames are already sorted by (session, id, inter) from load_and_sort
    for idx in range(len(sg_ind)):
        ind = sg_ind[idx]
        sg_e[idx] = e_i[ind]
        e_i[ind] += lam * sg_init_a[idx] * sg_pay[idx]

    # Map SG-level e_i to round-level initial rounds
    initial_mask = is_initial
    sg_indices_for_initial = data["round_sg_idx"][initial_mask]
    probs[initial_mask] = expit(alpha + beta * data["round_delta_rd"][initial_mask] + sg_e[sg_indices_for_initial])

    return probs, data["round_action"]


def log_loss_score(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def accuracy(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p >= 0.5) == y))


def mse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((y - p) ** 2))


def objective(params: np.ndarray, data: dict) -> float:
    alpha, beta, lam, p_CC_raw, p_CD_DC_raw, p_DD_raw = params
    p_CC = 1.0 / (1.0 + np.exp(-p_CC_raw))
    p_CD_DC = 1.0 / (1.0 + np.exp(-p_CD_DC_raw))
    p_DD = 1.0 / (1.0 + np.exp(-p_DD_raw))
    probs, actions = predict_probs(data, alpha, beta, lam, p_CC, p_CD_DC, p_DD)
    return log_loss_score(actions, probs)


def inv_sigmoid(p: float) -> float:
    return np.log(p / (1.0 - p))


def main() -> None:
    parser = argparse.ArgumentParser(description="IRL-SG prediction model (Appendix D)")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-estimate", action="store_true", help="Skip MLE; use paper defaults instead")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "results" / "next_action_prediction",
    )
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = load_and_sort(args.data)
    rng = np.random.default_rng(args.seed)

    # Stratified split by (g, l, delta): within each treatment, split sessions 80/20
    session_treatments = df.groupby("session")[["g", "l", "delta"]].first()
    session_treatments["_treatment"] = list(zip(session_treatments["g"], session_treatments["l"], session_treatments["delta"]))

    train_sessions = set()
    test_sessions = set()
    for _, grp in session_treatments.groupby("_treatment", sort=False):
        sess = grp.index.to_numpy()
        rng.shuffle(sess)
        n_test_grp = max(1, int(len(sess) * args.test_size))
        test_sessions.update(sess[:n_test_grp].tolist())
        train_sessions.update(sess[n_test_grp:].tolist())

    train_df = df[df["session"].isin(train_sessions)].copy()
    test_df = df[df["session"].isin(test_sessions)].copy()

    n_train_ind = train_df["id"].nunique()
    n_test_ind = test_df["id"].nunique()
    n_treatments = len(session_treatments["_treatment"].unique())
    print(f"sessions: {len(session_treatments)}, train: {len(train_sessions)} ({n_train_ind} individuals), "
          f"test: {len(test_sessions)} ({n_test_ind} individuals)")
    print(f"stratified on {n_treatments} unique (g, l, delta) treatments")

    print("Preprocessing (parsing JSON)...")
    train_data = preprocess(train_df)
    test_data = preprocess(test_df)
    print(f"  train: {len(train_data['round_action'])} rounds, test: {len(test_data['round_action'])} rounds")

    results_rows = []

    if not args.no_estimate:
        # MLE: minimize log-loss on training data
        # Probabilities parameterized via sigmoid to keep them in (0,1)
        x0 = np.array([
            PAPER_DEFAULTS["alpha"],
            PAPER_DEFAULTS["beta"],
            PAPER_DEFAULTS["lam"],
            inv_sigmoid(PAPER_DEFAULTS["p_CC"]),
            inv_sigmoid(PAPER_DEFAULTS["p_CD_DC"]),
            inv_sigmoid(PAPER_DEFAULTS["p_DD"]),
        ])
        print("Estimating parameters via MLE on training data...")
        result = minimize(
            objective,
            x0,
            args=(train_data,),
            method="Nelder-Mead",
            options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-8, "disp": True},
        )
        a_hat, b_hat, l_hat = result.x[0], result.x[1], result.x[2]
        pCC_hat = 1.0 / (1.0 + np.exp(-result.x[3]))
        pCD_hat = 1.0 / (1.0 + np.exp(-result.x[4]))
        pDD_hat = 1.0 / (1.0 + np.exp(-result.x[5]))
        print(f"Estimated: alpha={a_hat:.4f} beta={b_hat:.4f} lam={l_hat:.4f} "
              f"pCC={pCC_hat:.4f} pCD_DC={pCD_hat:.4f} pDD={pDD_hat:.4f}")
        print(f"  log-loss on train: {result.fun:.6f}")

        for label, data in [("train", train_data), ("test", test_data)]:
            probs, actions = predict_probs(data, a_hat, b_hat, l_hat, pCC_hat, pCD_hat, pDD_hat)
            ll = log_loss_score(actions, probs)
            acc = accuracy(actions, probs)
            m = mse(actions, probs)
            auc = roc_auc_score(actions, probs)
            print(f"  MLE {label:>5}: n={len(actions):>7}  accuracy={acc:.4f}  auc={auc:.4f}  log_loss={ll:.4f}  mse={m:.4f}")

        probs_train, _ = predict_probs(train_data, a_hat, b_hat, l_hat, pCC_hat, pCD_hat, pDD_hat)
        probs_test, actions_test = predict_probs(test_data, a_hat, b_hat, l_hat, pCC_hat, pCD_hat, pDD_hat)
        actions_train = train_data["round_action"]
        results_rows.append({
            "feature_spec": "irl_sg_mle",
            "n_hist": -1,
            "model": "irl_sg_mle",
            "train_rows": int(len(actions_train)),
            "test_rows": int(len(actions_test)),
            "train_accuracy": accuracy(actions_train, probs_train),
            "train_auc": roc_auc_score(actions_train, probs_train),
            "train_log_loss": log_loss_score(actions_train, probs_train),
            "train_mse": mse(actions_train, probs_train),
            "test_accuracy": accuracy(actions_test, probs_test),
            "test_auc": roc_auc_score(actions_test, probs_test),
            "test_log_loss": log_loss_score(actions_test, probs_test),
            "test_mse": mse(actions_test, probs_test),
        })

    # Also run with paper defaults for comparison
    alpha = PAPER_DEFAULTS["alpha"]
    beta = PAPER_DEFAULTS["beta"]
    lam = PAPER_DEFAULTS["lam"]
    p_CC = PAPER_DEFAULTS["p_CC"]
    p_CD_DC = PAPER_DEFAULTS["p_CD_DC"]
    p_DD = PAPER_DEFAULTS["p_DD"]
    print(f"\nPaper defaults: alpha={alpha} beta={beta} lam={lam} "
          f"pCC={p_CC} pCD_DC={p_CD_DC} pDD={p_DD}")

    for label, data in [("train", train_data), ("test", test_data)]:
        probs, actions = predict_probs(data, alpha, beta, lam, p_CC, p_CD_DC, p_DD)
        ll = log_loss_score(actions, probs)
        acc = accuracy(actions, probs)
        m = mse(actions, probs)
        print(f"  defaults {label:>5}: n={len(actions):>7}  accuracy={acc:.4f}  log_loss={ll:.4f}  mse={m:.4f}")

    probs_train_def, _ = predict_probs(train_data, alpha, beta, lam, p_CC, p_CD_DC, p_DD)
    probs_test_def, actions_test_def = predict_probs(test_data, alpha, beta, lam, p_CC, p_CD_DC, p_DD)
    actions_train_def = train_data["round_action"]
    results_rows.append({
        "feature_spec": "irl_sg",
        "n_hist": -1,
        "model": "irl_sg",
        "train_rows": int(len(actions_train_def)),
        "test_rows": int(len(actions_test_def)),
        "train_accuracy": accuracy(actions_train_def, probs_train_def),
        "train_auc": roc_auc_score(actions_train_def, probs_train_def), 
        "train_log_loss": log_loss_score(actions_train_def, probs_train_def),
        "train_mse": mse(actions_train_def, probs_train_def),
        "test_accuracy": accuracy(actions_test_def, probs_test_def),
        "test_auc": roc_auc_score(actions_test_def, probs_test_def),
        "test_log_loss": log_loss_score(actions_test_def, probs_test_def),
        "test_mse": mse(actions_test_def, probs_test_def),
    })

    results = pd.DataFrame(results_rows)
    out_path = args.outdir / f"next_action_results_model_irl_sg_seed_{args.seed}.csv"
    results.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
