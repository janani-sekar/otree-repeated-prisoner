"""
Convert experimental_data.csv (Fudenberg & Rehbinder format) to the
epsilon_test.feather format: one row per game, both players' actions/payoffs
stored as numpy arrays, 0=cooperate / 1=defect.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "experimental_data.csv"
STAGE = ROOT / "data" / "experimental_data_stage_games.csv"
OUTPUT = ROOT / "data" / "experimental_data_normalized.feather"


def parse_array(s: str) -> np.ndarray:
    return np.array(json.loads(s), dtype=float)


def flip_actions(arr: np.ndarray) -> np.ndarray:
    """Fudenberg: 1=cooperate, -1=defect  →  target: 0=cooperate, 1=defect."""
    return ((arr * -1 + 1) / 2).astype(int)


def main() -> None:
    raw = pd.read_csv(INPUT)
    stage = pd.read_csv(STAGE, usecols=["id", "session", "inter", "delta_rd", "num_rounds"])

    raw = raw.merge(stage, on=["id", "session", "inter"], how="left")

    # Parse action/payoff strings into lists so we can compare and store
    raw["c_parsed"] = raw["c"].apply(parse_array)
    raw["opp_c_parsed"] = raw["opp_c"].apply(parse_array)
    raw["payoff_parsed"] = raw["payoff"].apply(parse_array)

    rows = []
    game_counter = 0

    for (session, inter), grp in raw.groupby(["session", "inter"]):
        grp = grp.sort_values("id").reset_index(drop=True)
        used = set()

        for i in range(len(grp)):
            if i in used:
                continue
            row_a = grp.iloc[i]

            for j in range(i + 1, len(grp)):
                if j in used:
                    continue
                row_b = grp.iloc[j]

                if (np.array_equal(row_a["c_parsed"], row_b["opp_c_parsed"])
                        and np.array_equal(row_a["opp_c_parsed"], row_b["c_parsed"])):
                    used.add(i)
                    used.add(j)

                    p1_actions = flip_actions(row_a["c_parsed"])
                    p2_actions = flip_actions(row_b["c_parsed"])
                    p1_payoffs = row_a["payoff_parsed"]
                    p2_payoffs = row_b["payoff_parsed"]

                    delta = row_a["delta"]
                    g = row_a["g"]
                    l_val = row_a["l"]
                    delta_rd = row_a["delta_rd"] if "delta_rd" in row_a.index and pd.notna(row_a["delta_rd"]) else np.nan

                    rows.append({
                        "session_id": int(session),
                        "game_id": game_counter,
                        "paper": row_a["paper"],
                        "player1_id": int(row_a["id"]),
                        "player2_id": int(row_b["id"]),
                        "player1_actions": p1_actions,
                        "player2_actions": p2_actions,
                        "player1_payoffs": p1_payoffs,
                        "player2_payoffs": p2_payoffs,
                        "delta": delta,
                        "delta_rd": delta_rd,
                        "g": g,
                        "l": l_val,
                    })
                    game_counter += 1
                    break

    df = pd.DataFrame(rows)
    print(f"Input:  {len(raw):,} player-supergame rows")
    print(f"Output: {len(df):,} game rows ({game_counter} unique games)")
    print(f"Papers: {df['paper'].nunique()}")
    print(f"Columns: {list(df.columns)}")

    df.to_feather(OUTPUT)
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
