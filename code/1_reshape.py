import pandas as pd

def process_file(path):
    df = pd.read_csv(path)

    # Separate prisoner round columns and participant-level metadata
    prisoner_columns = [col for col in df.columns if col.startswith("prisoner.")]
    metadata_columns = [col for col in df.columns if not col.startswith("prisoner.")]

    # Reshape prisoner data to long format
    df_prisoner = df[["participant.code"] + prisoner_columns]
    prisoner_long = df_prisoner.melt(id_vars=["participant.code"], 
                                      var_name="round_var", 
                                      value_name="value")

    # Extract round number and variable name
    prisoner_long["round_number"] = prisoner_long["round_var"].str.extract(r"prisoner\.(\d+)\.")[0].astype(int)
    prisoner_long["variable"] = prisoner_long["round_var"].str.extract(r"prisoner\.\d+\.(.+)")

    # Pivot to get one row per player per round
    prisoner_long = prisoner_long.pivot(index=["participant.code", "round_number"], 
                                         columns="variable", 
                                         values="value").reset_index()

    # Prepare metadata: drop duplicated column names
    metadata = df[["participant.code"] + metadata_columns]
    metadata = metadata.loc[:, ~metadata.columns.duplicated()]

    # Merge metadata into long-format data
    prisoner_long = prisoner_long.merge(metadata, on="participant.code", how="left")

    # Drop unnecessary columns and put back session code
    session_code = prisoner_long["session.code"]
    prisoner_long = prisoner_long.iloc[:, :-23]
    prisoner_long.drop(columns=[
        "group.dieroll", 
        "player.timed_out_rounds_json", 
        "player.role"
    ], inplace=True)
    prisoner_long["session.code"] = session_code

    # Forward fill prolific_id
    prisoner_long = prisoner_long.sort_values(by=["participant.code", "round_number"])
    prisoner_long["player.prolific_id"] = (
        prisoner_long.groupby("participant.code")["player.prolific_id"].ffill()
    )

    # Drop bot or incomplete rows
    prisoner_long_filtered = prisoner_long.dropna(subset=["group.delta_value", "player.prolific_id"])

    # Add opponent mapping
    opponent_map = prisoner_long_filtered[[
        "participant.code", "round_number", "group.id_in_subsession", "session.code"
    ]]
    opponent_pairs = opponent_map.merge(
        opponent_map,
        on=["round_number", "group.id_in_subsession", "session.code"],
        suffixes=("", "_opponent")
    )
    opponent_pairs = opponent_pairs[opponent_pairs["participant.code"] != opponent_pairs["participant.code_opponent"]]
    prisoner_long_filtered = prisoner_long_filtered.merge(
        opponent_pairs[["participant.code", "round_number", "participant.code_opponent"]],
        on=["participant.code", "round_number"],
        how="left"
    ).rename(columns={"participant.code_opponent": "opponent"})
    prisoner_long_filtered.dropna(subset=["opponent"], inplace=True)

    return prisoner_long_filtered


# Process both files
df1 = process_file("data/pilot1.csv")
df2 = process_file("data/pilot2.csv")
df3 = process_file("data/pilot3.csv")

# Combine into one dataset
combined = pd.concat([df3], ignore_index=True)
combined.to_feather("data/pilot_combined_long.feather")
