"""
Bootstrap CIs for Transformer next-action prediction.

Fits the model ONCE on the same fixed stratified session-level train set as
IRL-SG (seed=0, test_size=0.2), then bootstraps the test set B times.

Token encoding (input):
  t=0 : start token = 4
  t>0 : (prev_player_coop * 2 + prev_opp_coop)  ->  DD=0 DC=1 CD=2 CC=3

Output: binary P(player cooperates at t) — matches IRL-SG evaluation unit.

--mask-r1 flag:
  If set, the round-1 (t=0) label is masked out from training AND evaluation,
  matching baseline models that require >=1 round of history.
  If not set, t=0 is kept: the model predicts the opening action from the
  start token alone (matches IRL-SG and the main-repo transformer setup).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Config (hardcoded, mirrors main repo cluster_transformer_p1 / cluster_lstm)
# ---------------------------------------------------------------------------

DATA_PATH    = Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv"
OUTDIR       = Path(__file__).resolve().parent.parent / "results" / "next_action_prediction"

SEED         = 0
TEST_SIZE    = 0.2
VAL_FRAC     = 0.2
N_BOOTSTRAP  = 1000

MAX_EPOCHS   = 100
BATCH_SIZE   = 32
LR           = 5e-4
PATIENCE     = 5
MIN_DELTA    = 1e-4
GRAD_CLIP    = 1.0

TRANSFORMER_EMBED_SIZE = 32
TRANSFORMER_NUM_HEADS  = 4
TRANSFORMER_NUM_LAYERS = 4
TRANSFORMER_DROPOUT    = 0.0

LSTM_EMBED_SIZE  = 6
LSTM_HIDDEN_SIZE = 64
LSTM_NUM_LAYERS  = 3
LSTM_DROPOUT     = 0.0

VOCAB_SIZE  = 5   # tokens 0-3 joint + 4 start
OUTPUT_SIZE = 2   # cooperate / defect
PAD_TOKEN   = 5   # used for batching


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 500):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class TransformerModel(nn.Module):
    def __init__(self, vocab_size=VOCAB_SIZE + 1, embed_size=TRANSFORMER_EMBED_SIZE,
                 num_heads=TRANSFORMER_NUM_HEADS, num_layers=TRANSFORMER_NUM_LAYERS,
                 output_size=OUTPUT_SIZE, pad_token_idx=PAD_TOKEN,
                 dropout=TRANSFORMER_DROPOUT):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_size, padding_idx=pad_token_idx)
        self.pos_encoder = PositionalEncoding(embed_size, dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_size, nhead=num_heads, dropout=dropout, batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers, enable_nested_tensor=False
        )
        self.fc = nn.Linear(embed_size, output_size)

    def forward(self, x):
        seq_len = x.size(1)
        embedded = self.embedding(x)
        embedded = self.pos_encoder(embedded)
        causal_mask = torch.triu(torch.ones(seq_len, seq_len, device=x.device), diagonal=1).bool()
        padding_mask = (x == self.embedding.padding_idx)
        transformer_out = self.transformer_encoder(
            embedded, mask=causal_mask, src_key_padding_mask=padding_mask
        )
        return self.fc(transformer_out)


class LSTMModel(nn.Module):
    def __init__(self, vocab_size=VOCAB_SIZE + 1, embed_size=LSTM_EMBED_SIZE,
                 hidden_size=LSTM_HIDDEN_SIZE, output_size=OUTPUT_SIZE,
                 pad_token_idx=PAD_TOKEN, dropout=LSTM_DROPOUT):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_size, padding_idx=pad_token_idx)
        self.lstm = nn.LSTM(embed_size, hidden_size, num_layers=LSTM_NUM_LAYERS,
                            dropout=dropout, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        embedded = self.embedding(x)
        lstm_out, _ = self.lstm(embedded)
        return self.fc(lstm_out)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_and_sort(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.sort_values(["session", "id", "inter"]).reset_index(drop=True)
    df["_actions"]     = df["c"].apply(json.loads)
    df["_opp_actions"] = df["opp_c"].apply(json.loads)
    return df


def make_split(df: pd.DataFrame, test_size: float, seed: int):
    session_treatments = df.groupby("session")[["g", "l", "delta"]].first()
    session_treatments["_treatment"] = list(
        zip(session_treatments["g"], session_treatments["l"],
            session_treatments["delta"])
    )
    treatment_groups = {}
    for key, grp in session_treatments.groupby("_treatment", sort=False):
        treatment_groups[key] = grp.index.to_numpy()

    rng = np.random.default_rng(seed)
    train_sessions, test_sessions = set(), set()
    for sessions in treatment_groups.values():
        shuffled = sessions.copy()
        rng.shuffle(shuffled)
        n_test = max(1, int(len(shuffled) * test_size))
        test_sessions.update(shuffled[:n_test].tolist())
        train_sessions.update(shuffled[n_test:].tolist())
    return train_sessions, test_sessions


def build_sequences(df: pd.DataFrame, mask_r1: bool):
    """
    Returns:
        tokens_list : list of 1-D int arrays, shape (T,) — input tokens
        labels_list : list of 1-D int arrays, shape (T,) — target actions
    """
    tokens_list, labels_list = [], []
    for _, row in df.iterrows():
        actions     = row["_actions"]
        opp_actions = row["_opp_actions"]
        T = len(actions)
        if T < 1:
            continue

        inp_tokens = [4]   # start token
        for t in range(T - 1):
            pm = 1 if actions[t] == 1 else 0
            po = 1 if opp_actions[t] == 1 else 0
            inp_tokens.append(pm * 2 + po)

        labels = [1 if a == 1 else 0 for a in actions]
        labels_arr = np.array(labels, dtype=np.int64)
        if mask_r1:
            labels_arr[0] = -1  # skip round-1 prediction (matches baseline n_hist>=1)
        tokens_list.append(np.array(inp_tokens, dtype=np.int64))
        labels_list.append(labels_arr)
    return tokens_list, labels_list


def collate(batch):
    tokens_list, labels_list = zip(*batch)
    max_len = max(len(t) for t in tokens_list)
    B = len(tokens_list)

    tokens_padded = torch.full((B, max_len), PAD_TOKEN, dtype=torch.long)
    labels_padded = torch.full((B, max_len), -1,        dtype=torch.long)

    for i, (t, l) in enumerate(zip(tokens_list, labels_list)):
        L = len(t)
        tokens_padded[i, :L] = torch.from_numpy(t)
        labels_padded[i, :L] = torch.from_numpy(l)

    return tokens_padded, labels_padded


class SeqDataset(torch.utils.data.Dataset):
    def __init__(self, tokens_list, labels_list):
        self.tokens = tokens_list
        self.labels = labels_list
    def __len__(self): return len(self.tokens)
    def __getitem__(self, i): return self.tokens[i], self.labels[i]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_model(model, tokens_list, labels_list, device,
                epochs=MAX_EPOCHS, lr=LR, batch_size=BATCH_SIZE, patience=PATIENCE,
                min_delta=MIN_DELTA, grad_clip_norm=GRAD_CLIP, val_frac=VAL_FRAC,
                seed=SEED, weight_decay=0.0, warmup_frac=0.0, label_smoothing=0.0):
    """Early stopping on held-out validation loss. Optional AdamW + cosine-decay
    with linear warmup, and label smoothing."""
    model.to(device)

    rng = np.random.default_rng(seed)
    n_total = len(tokens_list)
    idx = np.arange(n_total)
    rng.shuffle(idx)
    n_val = max(1, int(round(n_total * val_frac)))
    val_idx = idx[:n_val]
    tr_idx  = idx[n_val:]

    tr_tokens = [tokens_list[i] for i in tr_idx]
    tr_labels = [labels_list[i] for i in tr_idx]
    va_tokens = [tokens_list[i] for i in val_idx]
    va_labels = [labels_list[i] for i in val_idx]

    tr_loader = torch.utils.data.DataLoader(
        SeqDataset(tr_tokens, tr_labels),
        batch_size=batch_size, shuffle=True, collate_fn=collate,
    )
    va_loader = torch.utils.data.DataLoader(
        SeqDataset(va_tokens, va_labels),
        batch_size=batch_size, shuffle=False, collate_fn=collate,
    )

    if weight_decay > 0:
        optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    else:
        optim = torch.optim.Adam(model.parameters(), lr=lr)

    steps_per_epoch = max(1, len(tr_loader))
    total_steps  = steps_per_epoch * epochs
    warmup_steps = int(warmup_frac * total_steps)

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / max(1, warmup_steps)
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))

    sched = torch.optim.lr_scheduler.LambdaLR(optim, lr_lambda) if warmup_frac > 0 else None
    criterion = nn.CrossEntropyLoss(ignore_index=-1, label_smoothing=label_smoothing)

    best_val, no_improve = float("inf"), 0
    best_state = None
    for epoch in range(epochs):
        model.train()
        train_loss, n_tr = 0.0, 0
        for tokens, labels in tr_loader:
            tokens = tokens.to(device)
            labels = labels.to(device)
            logits = model(tokens)
            loss = criterion(logits.reshape(-1, 2), labels.reshape(-1))
            optim.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
            optim.step()
            if sched is not None:
                sched.step()
            train_loss += loss.item(); n_tr += 1

        model.eval()
        val_loss, n_va = 0.0, 0
        with torch.no_grad():
            for tokens, labels in va_loader:
                tokens = tokens.to(device)
                labels = labels.to(device)
                logits = model(tokens)
                loss = criterion(logits.reshape(-1, 2), labels.reshape(-1))
                val_loss += loss.item(); n_va += 1

        avg_tr = train_loss / max(1, n_tr)
        avg_va = val_loss   / max(1, n_va)
        cur_lr = optim.param_groups[0]["lr"]
        print(f"  epoch {epoch+1}: train={avg_tr:.4f} val={avg_va:.4f} lr={cur_lr:.2e}")

        if avg_va < best_val - min_delta:
            best_val, no_improve = avg_va, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            no_improve += 1
            if no_improve >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model


# ---------------------------------------------------------------------------
# Inference: get flat arrays of (y, p_coop) for all rounds in a split
# ---------------------------------------------------------------------------

@torch.no_grad()
def get_probs(model, tokens_list, labels_list, device, batch_size=128):
    model.eval()
    ds = SeqDataset(tokens_list, labels_list)
    loader = torch.utils.data.DataLoader(
        ds, batch_size=batch_size, shuffle=False, collate_fn=collate
    )
    all_y, all_p = [], []
    for tokens, labels in loader:
        tokens = tokens.to(device)
        labels = labels.to(device)
        logits = model(tokens)
        probs  = torch.softmax(logits, dim=-1)[..., 1]      # P(cooperate), (B, T)
        mask   = labels != -1
        all_y.append(labels[mask].cpu().numpy())
        all_p.append(probs[mask].cpu().numpy())
    return np.concatenate(all_y), np.concatenate(all_p)


@torch.no_grad()
def get_per_round_preds(model, tokens_list, labels_list, seq_meta, device):
    """Per-sequence per-round predictions. Returns rows of
    (session, id, inter, t, y, p) for each non-masked (label != -1) round.
    `seq_meta` is a list of (session, id, inter) triples aligned with tokens."""
    model.eval()
    rows = []
    for tokens, labels, meta in zip(tokens_list, labels_list, seq_meta):
        x = torch.from_numpy(tokens).unsqueeze(0).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=-1)[0, :, 1].cpu().numpy()
        session, ind_id, inter = meta
        for t, (y, p) in enumerate(zip(labels, probs)):
            if y == -1:
                continue
            rows.append({
                "session": session, "id": ind_id, "inter": int(inter),
                "t": int(t), "y": int(y), "p": float(p),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_arrays(y, p):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return {
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "auc":      float(roc_auc_score(y, p)),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "mse":      float(np.mean((y - p) ** 2)),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bootstrap CIs for Transformer next-action prediction")
    parser.add_argument("--mask-r1", dest="mask_r1", action="store_true",
                        help="Mask round-1 label (matches baseline n_hist>=1 evaluation)")
    parser.add_argument("--no-mask-r1", dest="mask_r1", action="store_false",
                        help="Keep round-1 label (predict opening move from start token)")
    parser.set_defaults(mask_r1=True)
    parser.add_argument("--lr",             type=float, default=LR)
    parser.add_argument("--max-epochs",     type=int,   default=MAX_EPOCHS)
    parser.add_argument("--patience",       type=int,   default=PATIENCE)
    parser.add_argument("--min-delta",      type=float, default=MIN_DELTA)
    parser.add_argument("--weight-decay",   type=float, default=0.0)
    parser.add_argument("--warmup-frac",    type=float, default=0.0,
                        help="Linear warmup fraction of total steps, then cosine decay to 0.")
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--tune", action="store_true",
                        help="Skip the 1000x bootstrap and the per-round CSV dump (for fast tuning).")
    parser.add_argument("--tag", type=str, default="",
                        help="Extra filename tag for tuning sweeps.")
    args = parser.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"Device: {device}")
    print(f"mask_r1: {args.mask_r1}")

    df = load_and_sort(DATA_PATH)
    print(f"{len(df):,} sequences loaded")

    train_sessions, test_sessions = make_split(df, TEST_SIZE, SEED)
    print(f"Train sessions: {len(train_sessions)}, Test sessions: {len(test_sessions)}")

    df_train = df[df["session"].isin(train_sessions)]
    df_test  = df[df["session"].isin(test_sessions)]

    train_tokens, train_labels = build_sequences(df_train, mask_r1=args.mask_r1)
    test_tokens,  test_labels  = build_sequences(df_test,  mask_r1=args.mask_r1)
    test_meta = list(zip(df_test["session"].tolist(),
                         df_test["id"].tolist(),
                         df_test["inter"].tolist()))
    print(f"Train rounds: {sum((l != -1).sum() for l in train_labels):,}, "
          f"Test rounds: {sum((l != -1).sum() for l in test_labels):,}")

    model_name = "transformer_mask_r1" if args.mask_r1 else "transformer_full"
    variant    = "mask_r1" if args.mask_r1 else "full"

    print(f"\nTraining {model_name} ...")
    print(f"  lr={args.lr} patience={args.patience} min_delta={args.min_delta} "
          f"max_epochs={args.max_epochs} weight_decay={args.weight_decay} "
          f"warmup_frac={args.warmup_frac} label_smoothing={args.label_smoothing}")
    torch.manual_seed(SEED)
    model = train_model(
        TransformerModel(), train_tokens, train_labels, device,
        epochs=args.max_epochs, lr=args.lr, patience=args.patience,
        min_delta=args.min_delta, weight_decay=args.weight_decay,
        warmup_frac=args.warmup_frac, label_smoothing=args.label_smoothing,
    )

    y_test, p_test = get_probs(model, test_tokens, test_labels, device)
    s = score_arrays(y_test, p_test)
    print(f"  {model_name}: acc={s['accuracy']:.4f} auc={s['auc']:.4f} nll={s['log_loss']:.4f}")

    if args.tune:
        print("(tune mode: skipping bootstrap and per-round CSV dump)")
        return

    preds_df = get_per_round_preds(model, test_tokens, test_labels, test_meta, device)
    preds_path = OUTDIR / f"test_preds_{model_name}_seed_{SEED}.csv"
    preds_df.to_csv(preds_path, index=False)
    print(f"Saved per-round test predictions to {preds_path}")

    results = []
    n = len(y_test)
    for b in tqdm(range(N_BOOTSTRAP), desc=f"Bootstrap {model_name}"):
        rng = np.random.default_rng(SEED + 1 + b)
        idx = rng.integers(0, n, size=n)
        s_b = score_arrays(y_test[idx], p_test[idx])
        results.append({
            "bootstrap_iter": b,
            "model":          model_name,
            "test_accuracy":  s_b["accuracy"],
            "test_auc":       s_b["auc"],
            "test_log_loss":  s_b["log_loss"],
            "test_mse":       s_b["mse"],
        })

    tag = f"_{args.tag}" if args.tag else ""
    out_path = OUTDIR / f"bootstrap_neural_{variant}{tag}_B{N_BOOTSTRAP}_seed_{SEED}.csv"
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")

    lo, med, hi = pd.DataFrame(results)["test_accuracy"].quantile([0.025, 0.5, 0.975])
    print(f"\n95% CI acc: {med:.4f} [{lo:.4f}, {hi:.4f}]")


if __name__ == "__main__":
    main()
