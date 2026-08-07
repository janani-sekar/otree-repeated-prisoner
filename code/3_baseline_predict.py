"""
Predict P1's next-round cooperate/defect from game parameters (g, l, delta) and
optional joint (P1, P2) n-gram history (last 1 .. last 5 joint action pairs).

Each round's joint state is encoded as "P1P2" (e.g. "10" = P1 cooperate, P2 defect).
An n-gram history string concatenates the last n such pairs, e.g. "10_01_11".

Feature specs:
- meta_only         (g, l, delta only)
- meta_hist_1..5    (+ last 1..5 joint-action pairs, one-hot)

Models: ols, lasso, svr, all

Train/test split is by sequence (row id), so all rounds from the same supergame stay
in the same fold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Lasso, LinearRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline, Pipeline
from sklearn.kernel_approximation import Nystroem
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import LinearSVR


HIST_SPECS = [0, 1, 2, 3, 4, 5]


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
    p1_bits: list[int],
    p2_bits: list[int],
    g: float,
    l: float,
    delta: float,
    seq_id: int,
    n_hist: int,
) -> pd.DataFrame:
    """Rows for one sequence and one history length n_hist.

    For n_hist = 0, this creates metadata-only rows (predict from round 1 onward).
    For n_hist >= 1, history is the last n_hist joint (P1,P2) pairs.
    """
    n_rounds = len(p1_bits)
    joint = [f"{p1_bits[t]}{p2_bits[t]}" for t in range(n_rounds)]

    rows = []
    start_t = max(1, n_hist)
    for t in range(start_t, n_rounds):
        row = {
            "seq_id": seq_id,
            "t": t,
            "y": p1_bits[t],
            "g": g,
            "l": l,
            "delta": delta,
        }
        if n_hist > 0:
            row["hist_str"] = "_".join(joint[t - n_hist : t])
        else:
            row["hist_str"] = "no_hist"
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def build_feature_frames(
    train: pd.DataFrame,
    test: pd.DataFrame,
    include_history: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """Return raw feature frames plus numeric and categorical column lists."""
    numeric_cols = ["g", "l", "delta"]
    categorical_cols = ["hist_str"] if include_history else []

    keep_cols = numeric_cols + categorical_cols
    X_train = train[keep_cols].copy()
    X_test = test[keep_cols].copy()

    return X_train, X_test, numeric_cols, categorical_cols


def make_model_pipeline(
    model_name: str,
    numeric_cols: list[str],
    categorical_cols: list[str],
    lasso_alpha: float,
    svr_c: float,
    svr_epsilon: float,
    svr_kernel: str,
) -> Pipeline:
    """Build preprocessing + estimator pipeline."""
    transformers = []
    if numeric_cols:
        transformers.append(
            ("num", StandardScaler(), numeric_cols)
        )
    if categorical_cols:
        transformers.append(
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical_cols,
            )
        )

    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")

    if model_name == "ols":
        estimator = LinearRegression()
    elif model_name == "lasso":
        estimator = Lasso(alpha=lasso_alpha, max_iter=10000)
    elif model_name == "svr":
        estimator = make_pipeline(
            Nystroem(kernel=svr_kernel, n_components=300, random_state=0),
            LinearSVR(C=svr_c, epsilon=svr_epsilon, max_iter=5000),
        )
    else:
        raise ValueError(f"unknown model_name={model_name!r}")

    return Pipeline(
        steps=[
            ("pre", preprocessor),
            ("model", estimator),
        ]
    )


def metrics_binary(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """Binary metrics treating p as predicted Pr(y=1)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    p = np.clip(p, 1e-15, 1 - 1e-15)

    acc = float(np.mean((p >= 0.5) == y))
    ll = float(log_loss(y, p, labels=[0, 1]))
    mse = float(np.mean((y - p) ** 2))
    auc = float(roc_auc_score(y, p))

    return {
        "auc": auc,
        "accuracy": acc,
        "log_loss": ll,
        "mse": mse,
        "n": float(len(y)),
    }


def fit_and_score(
    train: pd.DataFrame,
    test: pd.DataFrame,
    n_hist: int,
    model_name: str,
    lasso_alpha: float,
    svr_c: float,
    svr_epsilon: float,
    svr_kernel: str,
) -> tuple[dict[str, float], dict[str, float]]:
    include_history = n_hist > 0
    X_train, X_test, numeric_cols, categorical_cols = build_feature_frames(
        train=train,
        test=test,
        include_history=include_history,
    )

    y_train = train["y"].to_numpy(dtype=float)
    y_test = test["y"].to_numpy(dtype=float)

    pipe = make_model_pipeline(
        model_name=model_name,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        lasso_alpha=lasso_alpha,
        svr_c=svr_c,
        svr_epsilon=svr_epsilon,
        svr_kernel=svr_kernel,
    )
    pipe.fit(X_train, y_train)

    p_in = pipe.predict(X_train)
    p_out = pipe.predict(X_test)

    p_in = np.clip(p_in, 0.0, 1.0)
    p_out = np.clip(p_out, 0.0, 1.0)

    return metrics_binary(y_train, p_in), metrics_binary(y_test, p_out)


def spec_label(n_hist: int) -> str:
    if n_hist == 0:
        return "meta_only"
    return f"meta_hist_{n_hist}"


def build_expanded_data_for_spec(
    df: pd.DataFrame,
    train_ids: set[int],
    test_ids: set[int],
    n_hist: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_rows = []
    test_rows = []

    for i, row in df.iterrows():
        p1_bits = actions_to_bits(json.loads(row["c"]))
        p2_bits = actions_to_bits(json.loads(row["opp_c"]))
        g = float(row["g"])
        l = float(row["l"])
        delta = float(row["delta"])

        sub = expand_sequence(
            p1_bits=p1_bits,
            p2_bits=p2_bits,
            g=g,
            l=l,
            delta=delta,
            seq_id=i,
            n_hist=n_hist,
        )
        if sub.empty:
            continue

        if i in train_ids:
            train_rows.append(sub)
        elif i in test_ids:
            test_rows.append(sub)

    train_df = pd.concat(train_rows, ignore_index=True) if train_rows else pd.DataFrame()
    test_df = pd.concat(test_rows, ignore_index=True) if test_rows else pd.DataFrame()
    return train_df, test_df


def print_grid_table(results: pd.DataFrame, value_col: str, title: str) -> None:
    print(title)
    pivot = results.pivot(index="feature_spec", columns="model", values=value_col)
    pivot = pivot.reindex(index=[spec_label(n) for n in HIST_SPECS])
    print(pivot.round(4).to_string())
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="P1 next-action prediction with metadata and joint (P1,P2) n-grams")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv",
        help="CSV with columns c, opp_c (JSON P1/P2 actions), g, l, delta",
    )
    parser.add_argument("--test-size", type=float, default=0.2, help="Fraction of sequences in test set")
    parser.add_argument("--seed", type=int, default=42)

    parser.add_argument(
        "--model",
        type=str,
        default="all",
        choices=["ols", "lasso", "svr", "all"],
        help="Which model to run",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "results" / "next_action_prediction",
        help="Directory for CSV outputs",
    )

    parser.add_argument("--lasso-alpha", type=float, default=0.001)
    parser.add_argument("--svr-c", type=float, default=1.0)
    parser.add_argument("--svr-epsilon", type=float, default=0.05)
    parser.add_argument(
        "--svr-kernel",
        type=str,
        default="rbf",
        choices=["rbf", "linear", "poly", "sigmoid"],
    )

    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.data)
    rng = np.random.default_rng(args.seed)

    # Stratified split: within each (g, l, delta) treatment, 80/20 of sequences
    df["_treatment"] = df[["g", "l", "delta"]].apply(lambda r: (r["g"], r["l"], r["delta"]), axis=1)
    train_ids = set()
    test_ids = set()
    for _, grp in df.groupby("_treatment", sort=False):
        ids = grp.index.to_numpy()
        rng.shuffle(ids)
        n_test_grp = max(1, int(len(ids) * args.test_size))
        test_ids.update(ids[:n_test_grp].tolist())
        train_ids.update(ids[n_test_grp:].tolist())
    df.drop(columns=["_treatment"], inplace=True)

    print(f"sequences: {len(df)}, train sequences: {len(train_ids)}, test sequences: {len(test_ids)}")
    n_treatments = df[["g", "l", "delta"]].drop_duplicates().shape[0]
    print(f"stratified on {n_treatments} unique (g, l, delta) treatments")
    print()

    model_list = ["ols", "lasso", "svr"] if args.model == "all" else [args.model]

    results = []

    for n_hist in HIST_SPECS:
        train_df, test_df = build_expanded_data_for_spec(
            df=df,
            train_ids=train_ids,
            test_ids=test_ids,
            n_hist=n_hist,
        )

        if train_df.empty or test_df.empty:
            print(f"{spec_label(n_hist)}: skipped because train or test rows are empty after expansion")
            continue

        for model_name in model_list:
            in_s, out_s = fit_and_score(
                train=train_df,
                test=test_df,
                n_hist=n_hist,
                model_name=model_name,
                lasso_alpha=args.lasso_alpha,
                svr_c=args.svr_c,
                svr_epsilon=args.svr_epsilon,
                svr_kernel=args.svr_kernel,
            )

            row = {
                "feature_spec": spec_label(n_hist),
                "n_hist": n_hist,
                "model": model_name,
                "train_rows": int(train_df.shape[0]),
                "test_rows": int(test_df.shape[0]),
                "train_accuracy": in_s["accuracy"],
                "train_auc": in_s["auc"],
                "train_log_loss": in_s["log_loss"],
                "train_mse": in_s["mse"],
                "test_accuracy": out_s["accuracy"],
                "test_auc": out_s["auc"],
                "test_log_loss": out_s["log_loss"],
                "test_mse": out_s["mse"],
            }
            results.append(row)

            print(
                f"{spec_label(n_hist):>12} | {model_name:>5} | "
                f"train_rows={row['train_rows']:>6} test_rows={row['test_rows']:>6} | "
                f"test_acc={row['test_accuracy']:.4f} test_auc={row['test_auc']:.4f} test_ll={row['test_log_loss']:.4f} test_mse={row['test_mse']:.4f}"
            )

    print()

    results_df = pd.DataFrame(results)
    if results_df.empty:
        print("No results were generated.")
        return

    results_df = results_df.sort_values(["n_hist", "model"]).reset_index(drop=True)

    detail_path = args.outdir / f"next_action_results_model_{args.model}_seed_{args.seed}.csv"
    results_df.to_csv(detail_path, index=False)

    acc_grid = results_df.pivot(index="feature_spec", columns="model", values="test_accuracy")
    ll_grid = results_df.pivot(index="feature_spec", columns="model", values="test_log_loss")
    mse_grid = results_df.pivot(index="feature_spec", columns="model", values="test_mse")
    auc_grid = results_df.pivot(index="feature_spec", columns="model", values="test_auc")

    acc_grid = acc_grid.reindex(index=[spec_label(n) for n in HIST_SPECS])
    ll_grid = ll_grid.reindex(index=[spec_label(n) for n in HIST_SPECS])
    mse_grid = mse_grid.reindex(index=[spec_label(n) for n in HIST_SPECS])
    auc_grid = auc_grid.reindex(index=[spec_label(n) for n in HIST_SPECS])

    acc_path = args.outdir / f"grid_test_accuracy_model_{args.model}_seed_{args.seed}.csv"
    ll_path = args.outdir / f"grid_test_log_loss_model_{args.model}_seed_{args.seed}.csv"
    mse_path = args.outdir / f"grid_test_mse_model_{args.model}_seed_{args.seed}.csv"
    auc_path = args.outdir / f"grid_test_auc_model_{args.model}_seed_{args.seed}.csv"

    acc_grid.to_csv(acc_path)
    ll_grid.to_csv(ll_path)
    mse_grid.to_csv(mse_path)
    auc_grid.to_csv(auc_path)

    print_grid_table(results_df, "test_accuracy", "Test accuracy grid")
    print_grid_table(results_df, "test_log_loss", "Test log-loss grid")
    print_grid_table(results_df, "test_mse", "Test MSE grid")
    print_grid_table(results_df, "test_auc", "Test AUC grid")

    print(f"Saved detailed results to: {detail_path}")
    print(f"Saved accuracy grid to:   {acc_path}")
    print(f"Saved log-loss grid to:   {ll_path}")
    print(f"Saved MSE grid to:        {mse_path}")
    print(f"Saved AUC grid to:        {auc_path}")


if __name__ == "__main__":
    main()