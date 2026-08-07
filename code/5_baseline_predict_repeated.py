"""
Bootstrap CIs for baseline prediction models (OLS, Lasso).

Fits each model ONCE on a fixed SESSION-LEVEL stratified train set (same regime
as IRL-SG and the neural models), then bootstraps the test set B times
(sampling rows with replacement) to get CIs on test metrics.

Evaluation scope:
  - n_hist=0 (meta_only): evaluates on all rounds, INCLUDING t=0.
  - n_hist>=1:            evaluates on rounds t>=n_hist only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Lasso, Ridge
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from tqdm import tqdm

HIST_SPECS = [0, 1, 2, 3, 4, 5]
MODEL_LIST = ["ols", "lasso"]


def actions_to_bits(seq: list) -> list[int]:
    out = []
    for x in seq:
        if x == 1:
            out.append(1)
        elif x == -1:
            out.append(0)
        else:
            raise ValueError(f"unexpected action {x!r}, expected 1 or -1")
    return out


def expand_sequence(
    p1_bits: list[int], p2_bits: list[int],
    g: float, l: float, delta: float, seq_id: int, n_hist: int,
) -> pd.DataFrame:
    n_rounds = len(p1_bits)
    joint = [f"{p1_bits[t]}{p2_bits[t]}" for t in range(n_rounds)]
    rows = []
    # n_hist=0 (meta_only) includes t=0 since it has no history requirement.
    # n_hist>=1 starts at t=n_hist so full history is available.
    start_t = n_hist
    for t in range(start_t, n_rounds):
        row = {"seq_id": seq_id, "t": t, "y": p1_bits[t],
               "g": g, "l": l, "delta": delta}
        row["hist_str"] = "_".join(joint[t - n_hist : t]) if n_hist > 0 else "no_hist"
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def spec_label(n_hist: int) -> str:
    return "meta_only" if n_hist == 0 else f"meta_hist_{n_hist}"


def build_pipeline(n_hist: int, model_name: str, lasso_alpha: float) -> Pipeline:
    numeric_cols = ["g", "l", "delta"]
    categorical_cols = ["hist_str"] if n_hist > 0 else []

    transformers = [("num", StandardScaler(), numeric_cols)]
    if categorical_cols:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_cols))
    pre = ColumnTransformer(transformers=transformers, remainder="drop")

    if model_name == "ols":
        estimator = Ridge(alpha=1e-8)
    else:
        estimator = Lasso(alpha=lasso_alpha, max_iter=10000)

    return Pipeline([("pre", pre), ("model", estimator)])


def score_predictions(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return {
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "auc": float(roc_auc_score(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "mse": float(np.mean((y - p) ** 2)),
    }


def pre_expand_all(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    expanded = {}
    for n_hist in HIST_SPECS:
        chunks = []
        for i, row in df.iterrows():
            p1_bits = actions_to_bits(json.loads(row["c"]))
            p2_bits = actions_to_bits(json.loads(row["opp_c"]))
            sub = expand_sequence(
                p1_bits=p1_bits, p2_bits=p2_bits,
                g=float(row["g"]), l=float(row["l"]), delta=float(row["delta"]),
                seq_id=i, n_hist=n_hist,
            )
            if not sub.empty:
                chunks.append(sub)
        expanded[n_hist] = pd.concat(chunks, ignore_index=True)
        print(f"  n_hist={n_hist}: {len(expanded[n_hist]):,} rounds")
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CIs for baseline prediction (fixed model, bootstrap test)")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv")
    parser.add_argument("--n-bootstrap", type=int, default=1000)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lasso-alpha", type=float, default=0.001)
    parser.add_argument("--outdir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "results" / "next_action_prediction")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.data)
    print(f"{len(df):,} sequences loaded")

    print("Pre-expanding sequences for all n_hist specs...")
    expanded = pre_expand_all(df)
    print()

    # Session-level stratified split (matches IRL-SG and neural models)
    session_treatments = df.groupby("session")[["g", "l", "delta"]].first()
    session_treatments["_treatment"] = list(zip(
        session_treatments["g"], session_treatments["l"], session_treatments["delta"]
    ))
    session_groups: dict = {}
    for key, grp in session_treatments.groupby("_treatment", sort=False):
        session_groups[key] = grp.index.to_numpy()
    print(f"{len(session_groups)} treatment groups over {len(session_treatments)} sessions")

    rng_split = np.random.default_rng(args.seed)
    train_sessions: set = set()
    test_sessions: set = set()
    for sessions in session_groups.values():
        shuffled = sessions.copy()
        rng_split.shuffle(shuffled)
        n_test = max(1, int(len(shuffled) * args.test_size))
        test_sessions.update(shuffled[:n_test].tolist())
        train_sessions.update(shuffled[n_test:].tolist())
    print(f"Train sessions: {len(train_sessions)}, Test sessions: {len(test_sessions)}")

    train_seq_ids = df.index[df["session"].isin(train_sessions)].to_numpy()
    test_seq_ids  = df.index[df["session"].isin(test_sessions)].to_numpy()
    train_set = train_seq_ids
    test_set = test_seq_ids
    print(f"Train sequences: {len(train_set):,}, Test sequences: {len(test_set):,}")

    seq_id_arrays = {nh: exp["seq_id"].to_numpy() for nh, exp in expanded.items()}

    # Fit all models once, cache test predictions
    feature_cols_map = {}
    for n_hist in HIST_SPECS:
        feature_cols_map[n_hist] = ["g", "l", "delta"] + (["hist_str"] if n_hist > 0 else [])

    print("\nFitting models on train set...")
    fitted: dict[tuple[int, str], np.ndarray] = {}
    test_y: dict[int, np.ndarray] = {}
    test_dfs: dict[int, pd.DataFrame] = {}

    for n_hist in HIST_SPECS:
        exp = expanded[n_hist]
        sid = seq_id_arrays[n_hist]
        train_df = exp[np.isin(sid, train_set)]
        test_df = exp[np.isin(sid, test_set)]

        if train_df.empty or test_df.empty:
            continue

        keep = feature_cols_map[n_hist]
        y_train = train_df["y"].to_numpy(dtype=float)
        y_test = test_df["y"].to_numpy(dtype=float)
        test_y[n_hist] = y_test
        test_dfs[n_hist] = test_df.reset_index(drop=True)

        for model_name in MODEL_LIST:
            pipe = build_pipeline(n_hist, model_name, args.lasso_alpha)
            pipe.fit(train_df[keep], y_train)
            p = np.clip(pipe.predict(test_df[keep]), 1e-15, 1 - 1e-15)
            fitted[(n_hist, model_name)] = p
            s = score_predictions(y_test, p)
            print(f"  {spec_label(n_hist):>14} {model_name:>5}: acc={s['accuracy']:.4f} auc={s['auc']:.4f}")

    # Export per-round test predictions for OLS meta_only (used for by-seq-len fig).
    if (0, "ols") in fitted:
        meta_cols = df[["session", "id", "inter"]]
        preds_df = test_dfs[0][["seq_id", "t", "y"]].copy()
        preds_df["p"] = fitted[(0, "ols")]
        preds_df = preds_df.merge(
            meta_cols, left_on="seq_id", right_index=True, how="left"
        )
        preds_path = args.outdir / f"test_preds_ols_meta_only_seed_{args.seed}.csv"
        preds_df[["session", "id", "inter", "t", "y", "p"]].to_csv(preds_path, index=False)
        print(f"\nSaved per-round test predictions (OLS meta_only) to {preds_path}")

    # Bootstrap the test set
    print(f"\nBootstrapping test set {args.n_bootstrap} times...")
    results = []

    for b in tqdm(range(args.n_bootstrap), desc="Bootstrap test"):
        rng = np.random.default_rng(args.seed + 1 + b)

        for n_hist in HIST_SPECS:
            if n_hist not in test_y:
                continue
            y = test_y[n_hist]
            n = len(y)
            idx = rng.integers(0, n, size=n)
            y_boot = y[idx]

            for model_name in MODEL_LIST:
                key = (n_hist, model_name)
                if key not in fitted:
                    continue
                p_boot = fitted[key][idx]
                s = score_predictions(y_boot, p_boot)
                results.append({
                    "bootstrap_iter": b,
                    "feature_spec": spec_label(n_hist),
                    "n_hist": n_hist,
                    "model": model_name,
                    "test_accuracy": s["accuracy"],
                    "test_auc": s["auc"],
                    "test_log_loss": s["log_loss"],
                    "test_mse": s["mse"],
                })

    results_df = pd.DataFrame(results)
    out_path = args.outdir / f"bootstrap_baseline_B{args.n_bootstrap}_seed_{args.seed}.csv"
    results_df.to_csv(out_path, index=False)

    print(f"\nSaved {len(results_df):,} rows to {out_path}")

    print("\n95% CIs on test accuracy:")
    for spec in [spec_label(n) for n in HIST_SPECS]:
        for model in MODEL_LIST:
            sub = results_df[(results_df["feature_spec"] == spec) & (results_df["model"] == model)]
            if sub.empty:
                continue
            lo, med, hi = sub["test_accuracy"].quantile([0.025, 0.5, 0.975])
            print(f"  {spec:>14} {model:>5}: {med:.4f} [{lo:.4f}, {hi:.4f}]")


if __name__ == "__main__":
    main()
