"""
Convert player_pair_sequences.csv (oTree format) to the epsilon_test.feather
format: one row per game, both players' actions/payoffs as numpy arrays,
0=cooperate / 1=defect, payoffs normalized so CC=1, DD=0, DC=1+g, CD=-l.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "player_pair_sequences.csv"
OUTPUT = ROOT / "data" / "otree_normalized.feather"


def flip_action(a: int) -> int:
    """oTree: 1=cooperate, 0=defect → target: 0=cooperate, 1=defect."""
    return 1 - a


def main() -> None:
    raw = pd.read_csv(INPUT)

    games = raw.groupby(["session.code", "group.id_in_subsession"])
    rows = []

    for (session_code, group_id), grp in games:
        assert len(grp) == 2, f"Expected 2 rows per game, got {len(grp)}"
        grp = grp.sort_values("player.id_in_group").reset_index(drop=True)
        r1 = grp.iloc[0]
        r2 = grp.iloc[1]

        cc = r1["group.game_payoff_cooperate_cooperate"]
        dd = r1["group.game_payoff_both_defect"]
        dc = r1["group.game_payoff_betray"]
        cd = r1["group.game_payoff_betrayed"]
        scale = cc - dd

        g = (dc - cc) / scale
        l_val = (cc - cd) / scale

        decs_1 = json.loads(r1["decision_tuple"])
        decs_2 = json.loads(r2["decision_tuple"])
        pays_1 = json.loads(r1["payoff_tuple"])
        pays_2 = json.loads(r2["payoff_tuple"])

        p1_actions = np.array([flip_action(d[0]) for d in decs_1], dtype=int)
        p2_actions = np.array([flip_action(d[0]) for d in decs_2], dtype=int)

        p1_payoffs = np.array([(p[0] - dd) / scale for p in pays_1])
        p2_payoffs = np.array([(p[0] - dd) / scale for p in pays_2])

        delta = r1["group.delta_value"]

        rows.append({
            "session_id": session_code,
            "game_id": len(rows),
            "player1_id": r1["participant.code"],
            "player2_id": r2["participant.code"],
            "player1_actions": p1_actions,
            "player2_actions": p2_actions,
            "player1_payoffs": p1_payoffs,
            "player2_payoffs": p2_payoffs,
            "delta": delta,
            "g": g,
            "l": l_val,
        })

    df = pd.DataFrame(rows)
    print(f"Input:  {len(raw):,} player rows")
    print(f"Output: {len(df):,} game rows")
    print(f"Sessions: {df['session_id'].nunique()}")
    print(f"Columns: {list(df.columns)}")

    # Sanity check
    r = df.iloc[0]
    print(f"\nSample row 0: g={r.g:.4f}, l={r.l:.4f}, delta={r.delta}")
    print(f"  p1_actions={r.player1_actions[:5]}...")
    print(f"  p1_payoffs={r.player1_payoffs[:5]}...")

    df.to_feather(OUTPUT)
    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()
