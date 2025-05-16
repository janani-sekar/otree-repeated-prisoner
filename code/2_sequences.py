import pandas as pd
import json

# Load the long-format combined data
df = pd.read_feather("data/pilot_combined_long.feather")
df = df.sort_values(by=["participant.code", "round_number"])
df.dropna(inplace=True)
print(df.columns)

# Group and aggregate player-only sequences (optional output)
sequences_df = df.groupby("participant.code").agg({
    "player.decision": lambda x: list(x),
    "player.payoff": lambda x: list(x),
    "player.timeout_occurred": lambda x: list(x),
    "player.prolific_id": "first",
    "player.id_in_group": "first",
    "group.delta_value": "first",
    "opponent": "first",
    "group.id_in_subsession": "first",
    "session.code": "first",
    "group.game_payoff_betray": "first",
    "group.game_payoff_betrayed": "first",
    "group.game_payoff_both_defect": "first",
    "group.game_payoff_cooperate_cooperate": "first"
}).reset_index()
sequences_df.to_feather("data/player_sequences.feather")

# Rename opponent columns for merge
opp_df = df[[
    "round_number", 
    "participant.code", 
    "player.decision", 
    "player.payoff", 
    "player.timeout_occurred",
    "group.id_in_subsession", 
    "session.code"
]].rename(columns={
    "participant.code": "opponent",
    "player.decision": "opponent_decision",
    "player.payoff": "opponent_payoff",
    "player.timeout_occurred": "opponent_timeout_occurred",
    "group.id_in_subsession": "group.id_in_subsession_opp",
    "session.code": "session.code_opp"
})

# Merge player and opponent decisions
df_pairs = df.merge(
    opp_df,
    on=["opponent", "round_number"],
    how="left",
    suffixes=("", "_opp")
)

# Ensure match within session and group
df_pairs = df_pairs[
    (df_pairs["group.id_in_subsession"] == df_pairs["group.id_in_subsession_opp"]) &
    (df_pairs["session.code"] == df_pairs["session.code_opp"])
]

# Map decisions to binary
decision_map = {"Cooperate": 1, "Defect": 0}
df_pairs["player.decision"] = df_pairs["player.decision"].map(decision_map)
df_pairs["opponent_decision"] = df_pairs["opponent_decision"].map(decision_map)

# Create zipped decision and payoff tuples
df_pairs = df_pairs.sort_values(by=["participant.code", "round_number"])
df_pairs["decision_tuple"] = list(zip(df_pairs["player.decision"], df_pairs["opponent_decision"]))
df_pairs["payoff_tuple"] = list(zip(df_pairs["player.payoff"], df_pairs["opponent_payoff"]))
df_pairs["timeout_tuple"] = list(zip(df_pairs["player.timeout_occurred"], df_pairs["opponent_timeout_occurred"]))

# Aggregate to participant-level
paired_sequences_df = df_pairs.groupby("participant.code").agg({
    "decision_tuple": lambda x: list(x),
    "payoff_tuple": lambda x: list(x),
    "timeout_tuple": lambda x: list(x),
    "player.prolific_id": "first",
    "player.id_in_group": "first",
    "group.delta_value": "first",
    "opponent": "first",
    "group.id_in_subsession": "first",
    "session.code": "first",
    "group.game_payoff_betray": "first",
    "group.game_payoff_betrayed": "first",
    "group.game_payoff_both_defect": "first",
    "group.game_payoff_cooperate_cooperate": "first"
}).reset_index()

# Serialize decision and payoff tuples as JSON arrays-of-arrays
paired_sequences_df["decision_tuple"] = paired_sequences_df["decision_tuple"].apply(
    lambda lst: json.dumps([[int(a), int(b)] for a, b in lst])
)
paired_sequences_df["payoff_tuple"] = paired_sequences_df["payoff_tuple"].apply(
    lambda lst: json.dumps([[a, b] for a, b in lst])
)
paired_sequences_df["timeout_tuple"] = paired_sequences_df["timeout_tuple"].apply(
    lambda lst: json.dumps([[int(a), int(b)] for a, b in lst])
)

# Save as Feather
paired_sequences_df.to_feather("data/player_pair_sequences.feather")
