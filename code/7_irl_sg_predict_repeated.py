"""
Bootstrap CIs for IRL-SG prediction model.

Fits MLE and paper-defaults ONCE on a fixed train set, then bootstraps the
test set B times (sampling rounds with replacement) for confidence intervals.

--mask-r1 flag (evaluation only): if set, round-0 rows are excluded from the
test set before scoring and bootstrapping. Training (MLE) is unaffected.
This matches the evaluation scope of baseline n-gram OLS and the masked
Transformer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution
from scipy.special import expit
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

PAPER_DEFAULTS = dict(alpha=-0.268, beta=1.291, lam=0.182, p_CC=0.995, p_CD_DC=0.355, p_DD=0.012)

X0 = np.array([
    PAPER_DEFAULTS["alpha"], PAPER_DEFAULTS["beta"], PAPER_DEFAULTS["lam"],
    np.log(PAPER_DEFAULTS["p_CC"] / (1 - PAPER_DEFAULTS["p_CC"])),
    np.log(PAPER_DEFAULTS["p_CD_DC"] / (1 - PAPER_DEFAULTS["p_CD_DC"])),
    np.log(PAPER_DEFAULTS["p_DD"] / (1 - PAPER_DEFAULTS["p_DD"])),
])

BOUNDS = [
    (-5.0, 5.0),
    (-10.0, 10.0),
    (-2.0, 2.0),
    (-8.0, 8.0),
    (-8.0, 8.0),
    (-8.0, 8.0),
]


def load_and_sort(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.sort_values(["session", "id", "inter"]).reset_index(drop=True)
    df["Delta_RD"] = df["delta"] - (df["g"] + df["l"]) / (1 + df["g"] + df["l"])
    df["_actions"] = df["c"].apply(json.loads)
    df["_opp_actions"] = df["opp_c"].apply(json.loads)
    df["_payoffs"] = df["payoff"].apply(json.loads)
    return df


def preprocess(df: pd.DataFrame) -> dict:
    round_action = []
    round_prev_joint = []
    round_delta_rd = []
    round_individual = []
    round_sg_idx = []

    sg_individual = []
    sg_delta_rd = []
    sg_initial_action = []
    sg_total_payoff = []
    sg_order = []

    individual_map = {}
    ind_counter = 0

    for _, row in df.iterrows():
        key = (row["session"], row["id"])
        if key not in individual_map:
            individual_map[key] = ind_counter
            ind_counter += 1
        ind_id = individual_map[key]

        actions = row["_actions"]
        opp_actions = row["_opp_actions"]
        payoffs = row["_payoffs"]
        delta_rd = row["Delta_RD"]

        for t in range(len(actions)):
            round_action.append(1 if actions[t] == 1 else 0)
            round_individual.append(ind_id)
            round_sg_idx.append(len(sg_individual))
            round_delta_rd.append(delta_rd)

            if t == 0:
                round_prev_joint.append(-1)
            else:
                pm = 1 if actions[t - 1] == 1 else 0
                po = 1 if opp_actions[t - 1] == 1 else 0
                round_prev_joint.append(pm * 2 + po)

        sg_individual.append(ind_id)
        sg_delta_rd.append(delta_rd)
        sg_initial_action.append(1.0 if actions[0] == 1 else -1.0)
        sg_total_payoff.append(sum(payoffs))
        sg_order.append(row["inter"])

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


def predict_probs(
    data: dict, alpha: float, beta: float, lam: float,
    p_CC: float, p_CD_DC: float, p_DD: float,
) -> tuple[np.ndarray, np.ndarray]:
    prev = data["round_prev_joint"]
    probs = np.empty(len(prev), dtype=np.float64)

    is_initial = prev == -1
    probs[prev == 3] = p_CC
    probs[prev == 0] = p_DD
    probs[(prev == 1) | (prev == 2)] = p_CD_DC

    sg_ind = data["sg_individual"]
    sg_init_a = data["sg_initial_action"]
    sg_pay = data["sg_total_payoff"]

    e_i = np.zeros(data["n_individuals"], dtype=np.float64)
    sg_e = np.empty(len(sg_ind), dtype=np.float64)

    for idx in range(len(sg_ind)):
        ind = sg_ind[idx]
        sg_e[idx] = e_i[ind]
        e_i[ind] += lam * sg_init_a[idx] * sg_pay[idx]

    sg_idx = data["round_sg_idx"][is_initial]
    probs[is_initial] = expit(alpha + beta * data["round_delta_rd"][is_initial] + sg_e[sg_idx])

    return probs, data["round_action"]


def log_loss_score(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def accuracy(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p >= 0.5) == y))


def mse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((y - p) ** 2))


def score_arrays(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return {
        "accuracy": accuracy(y, p),
        "auc": float(roc_auc_score(y, p)),
        "log_loss": log_loss_score(y, p),
        "mse": mse(y, p),
    }


def objective(params: np.ndarray, data: dict) -> float:
    alpha, beta, lam, p_CC_raw, p_CD_DC_raw, p_DD_raw = params
    probs, actions = predict_probs(
        data, alpha, beta, lam,
        expit(p_CC_raw), expit(p_CD_DC_raw), expit(p_DD_raw),
    )
    return log_loss_score(actions, probs)


def fit_mle_blackbox(train_data: dict, seed: int) -> np.ndarray:
    res = differential_evolution(
        func=lambda x: objective(np.asarray(x, dtype=np.float64), train_data),
        bounds=BOUNDS,
        strategy="best1bin",
        maxiter=200,
        popsize=15,
        tol=1e-4,
        mutation=(0.5, 1.0),
        recombination=0.7,
        polish=False,
        seed=seed,
        updating="deferred",
        workers=1,
    )
    return np.asarray(res.x, dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CIs for IRL-SG (fixed model, bootstrap test)")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv")
    parser.add_argument("--n-bootstrap", type=int, default=1000)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-mle", action="store_true", help="Skip MLE (paper defaults only)")
    parser.add_argument("--mask-r1", action="store_true",
                        help="Exclude t=0 rounds from eval/bootstrap (match baseline n-gram scope)")
    parser.add_argument("--outdir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "results" / "next_action_prediction")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = load_and_sort(args.data)
    print(f"{len(df):,} rows loaded")

    # Single stratified session-level train/test split
    session_treatments = df.groupby("session")[["g", "l", "delta"]].first()
    session_treatments["_treatment"] = list(
        zip(session_treatments["g"], session_treatments["l"], session_treatments["delta"])
    )
    treatment_groups = {}
    for key, grp in session_treatments.groupby("_treatment", sort=False):
        treatment_groups[key] = grp.index.to_numpy()

    rng_split = np.random.default_rng(args.seed)
    train_sessions, test_sessions = set(), set()
    for sessions in treatment_groups.values():
        shuffled = sessions.copy()
        rng_split.shuffle(shuffled)
        n_test = max(1, int(len(shuffled) * args.test_size))
        test_sessions.update(shuffled[:n_test].tolist())
        train_sessions.update(shuffled[n_test:].tolist())

    train_data = preprocess(df[df["session"].isin(train_sessions)])
    test_data = preprocess(df[df["session"].isin(test_sessions)])
    print(f"Train sessions: {len(train_sessions)}, Test sessions: {len(test_sessions)}")
    print(f"Train rounds: {len(train_data['round_action']):,}, Test rounds: {len(test_data['round_action']):,}")

    # Get test predictions for paper defaults
    print("\nComputing test predictions with paper defaults...")
    probs_default, actions_test = predict_probs(test_data, **PAPER_DEFAULTS)

    # Optionally drop t=0 rounds from eval (training is unaffected).
    test_keep = np.ones_like(actions_test, dtype=bool) if not args.mask_r1 \
        else (test_data["round_prev_joint"] != -1)
    print(f"Eval scope: mask_r1={args.mask_r1} -> {test_keep.sum():,} / {len(test_keep):,} rounds")

    s = score_arrays(actions_test[test_keep], probs_default[test_keep])
    print(f"  defaults: acc={s['accuracy']:.4f} auc={s['auc']:.4f}")

    # Get test predictions for MLE
    probs_mle = None
    if not args.no_mle:
        print("Fitting MLE on train set...")
        theta = fit_mle_blackbox(train_data, seed=args.seed)
        a, be, la = theta[0], theta[1], theta[2]
        probs_mle, _ = predict_probs(
            test_data, a, be, la, expit(theta[3]), expit(theta[4]), expit(theta[5]),
        )
        s = score_arrays(actions_test[test_keep], probs_mle[test_keep])
        print(f"  MLE:      acc={s['accuracy']:.4f} auc={s['auc']:.4f}")
        print(f"  params:   alpha={a:.3f} beta={be:.3f} lam={la:.3f} "
              f"p_CC={expit(theta[3]):.3f} p_CD_DC={expit(theta[4]):.3f} p_DD={expit(theta[5]):.3f}")

    # Bootstrap the test set (within the eval scope)
    print(f"\nBootstrapping test set {args.n_bootstrap} times...")
    y = actions_test[test_keep]
    probs_default = probs_default[test_keep]
    if probs_mle is not None:
        probs_mle = probs_mle[test_keep]
    n = len(y)
    results = []

    default_model_name = "irl_sg_mask_r1" if args.mask_r1 else "irl_sg"
    mle_model_name     = "irl_sg_mle_mask_r1" if args.mask_r1 else "irl_sg_mle"

    for b in tqdm(range(args.n_bootstrap), desc="Bootstrap test"):
        rng = np.random.default_rng(args.seed + 1 + b)
        idx = rng.integers(0, n, size=n)
        y_boot = y[idx]

        p_boot = probs_default[idx]
        s = score_arrays(y_boot, p_boot)
        results.append({
            "bootstrap_iter": b, "model": default_model_name,
            "test_accuracy": s["accuracy"], "test_auc": s["auc"],
            "test_log_loss": s["log_loss"], "test_mse": s["mse"],
        })

        if probs_mle is not None:
            p_boot = probs_mle[idx]
            s = score_arrays(y_boot, p_boot)
            results.append({
                "bootstrap_iter": b, "model": mle_model_name,
                "test_accuracy": s["accuracy"], "test_auc": s["auc"],
                "test_log_loss": s["log_loss"], "test_mse": s["mse"],
            })

    results_df = pd.DataFrame(results)
    tag = "defaults" if args.no_mle else "both"
    if args.mask_r1:
        tag = f"{tag}_mask_r1"
    out_path = args.outdir / f"bootstrap_irl_sg_{tag}_B{args.n_bootstrap}_seed_{args.seed}.csv"
    results_df.to_csv(out_path, index=False)

    print(f"\nSaved {len(results_df):,} rows to {out_path}")

    print("\n95% CIs on test accuracy:")
    for model in results_df["model"].unique():
        sub = results_df[results_df["model"] == model]
        lo, med, hi = sub["test_accuracy"].quantile([0.025, 0.5, 0.975])
        print(f"  {model:>12}: {med:.4f} [{lo:.4f}, {hi:.4f}]")


if __name__ == "__main__":
    main()
