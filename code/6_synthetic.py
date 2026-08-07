"""
Synthetic repeated prisoner's dilemma: two LLMs play against each other.

Samples (g, l, delta) treatments from the experimental data, draws supergame
lengths from Geometric(1 - delta), and prompts two LLM players each round.
Both players are queried in parallel each round (truly simultaneous).
Output matches experimental_data.csv schema for reuse with existing analyses.

Tracks token usage and stops if estimated cost exceeds --cost-limit.

Supports both OpenAI and Google Gemini backends.
Keys are read from a .env file in the project root (OPENAI_API_KEY / GOOGLE_API_KEY).
"""

from __future__ import annotations

import argparse
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Action(BaseModel):
    action: str  # "Cooperate" or "Defect"


SYSTEM_PROMPT = """\
You are playing a repeated two-player game. Each round, you and your opponent \
simultaneously choose either Cooperate or Defect.

Payoffs each round (you, opponent):
- Both Cooperate:                ({cc_you}, {cc_opp})
- You Cooperate, Opponent Defects: ({cd_you}, {cd_opp})
- You Defect, Opponent Cooperates: ({dc_you}, {dc_opp})
- Both Defect:                   ({dd_you}, {dd_opp})

Each round, there is a {end_prob:.0%} chance the game ends. \
Do what you have to in order to maximize your payoff."""


class CostTracker:
    def __init__(self, limit: float):
        self.limit = limit
        self.input_tokens = 0
        self.output_tokens = 0
        self._cost_per_input = 0.0
        self._cost_per_output = 0.0

    def set_pricing(self, per_input: float, per_output: float) -> None:
        self._cost_per_input = per_input
        self._cost_per_output = per_output

    @property
    def cost(self) -> float:
        return (self.input_tokens * self._cost_per_input
                + self.output_tokens * self._cost_per_output)

    @property
    def exceeded(self) -> bool:
        return self.cost >= self.limit

    def add(self, input_tok: int, output_tok: int) -> None:
        self.input_tokens += input_tok
        self.output_tokens += output_tok


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------

class LLMBackend(ABC):
    @abstractmethod
    def create_player(self, model_name: str, system_prompt: str) -> object:
        ...

    @abstractmethod
    def query_action(self, player: object, prompt: str, temperature: float,
                     tracker: CostTracker) -> int:
        ...


class GeminiBackend(LLMBackend):
    # Gemini 2.0 Flash pricing (USD per token)
    INPUT_PRICE = 0.10 / 1_000_000
    OUTPUT_PRICE = 0.40 / 1_000_000

    def __init__(self):
        import google.generativeai as genai
        self._genai = genai
        genai.configure()

    def create_player(self, model_name: str, system_prompt: str) -> object:
        return self._genai.GenerativeModel(
            model_name,
            system_instruction=system_prompt,
            generation_config=self._genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema={"type": "object", "properties": {"action": {"type": "string", "enum": ["Cooperate", "Defect"]}}, "required": ["action"]},
            ),
        )

    def query_action(self, player, prompt: str, temperature: float,
                     tracker: CostTracker) -> int:
        resp = player.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(
                temperature=temperature,
            ),
        )
        meta = resp.usage_metadata
        tracker.add(meta.prompt_token_count, meta.candidates_token_count)
        parsed = json.loads(resp.text)
        return 1 if parsed["action"].lower().startswith("c") else 0


class OpenAIBackend(LLMBackend):
    # GPT-4o-mini pricing; override with set_pricing if using a different model
    INPUT_PRICE = 0.15 / 1_000_000
    OUTPUT_PRICE = 0.60 / 1_000_000

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI()

    def create_player(self, model_name: str, system_prompt: str) -> object:
        return {"model": model_name, "system_prompt": system_prompt}

    def query_action(self, player: dict, prompt: str, temperature: float,
                     tracker: CostTracker) -> int:
        resp = self._client.beta.chat.completions.parse(
            model=player["model"],
            messages=[
                {"role": "system", "content": player["system_prompt"]},
                {"role": "user", "content": prompt},
            ],
            response_format=Action,
            temperature=temperature,
        )
        usage = resp.usage
        tracker.add(usage.prompt_tokens, usage.completion_tokens)
        parsed = resp.choices[0].message.parsed
        return 1 if parsed.action.lower().startswith("c") else 0


def get_backend(model_name: str) -> LLMBackend:
    if model_name.startswith("gemini"):
        return GeminiBackend()
    return OpenAIBackend()


def get_pricing(model_name: str) -> tuple[float, float]:
    """Return (input_price, output_price) per token for known models."""
    if model_name.startswith("gemini"):
        return GeminiBackend.INPUT_PRICE, GeminiBackend.OUTPUT_PRICE
    if "gpt-4o-mini" in model_name:
        return 0.15 / 1_000_000, 0.60 / 1_000_000
    if "gpt-4o" in model_name:
        return 2.50 / 1_000_000, 10.00 / 1_000_000
    if "gpt-4.1" in model_name and "mini" in model_name:
        return 0.40 / 1_000_000, 1.60 / 1_000_000
    if "gpt-4.1" in model_name and "nano" in model_name:
        return 0.10 / 1_000_000, 0.40 / 1_000_000
    if "gpt-4.1" in model_name:
        return 2.00 / 1_000_000, 8.00 / 1_000_000
    if "o3-mini" in model_name:
        return 1.10 / 1_000_000, 4.40 / 1_000_000
    # fallback: assume roughly gpt-4o-mini pricing
    return 0.15 / 1_000_000, 0.60 / 1_000_000


# ---------------------------------------------------------------------------
# Game logic
# ---------------------------------------------------------------------------

def load_treatments(data_path: Path) -> pd.DataFrame:
    df = pd.read_csv(data_path, usecols=["g", "l", "delta"])
    return df.drop_duplicates().reset_index(drop=True)


def make_system_prompt(g: float, l: float, delta: float) -> str:
    return SYSTEM_PROMPT.format(
        cc_you=1.0, cc_opp=1.0,
        cd_you=round(-l, 4), cd_opp=round(1 + g, 4),
        dc_you=round(1 + g, 4), dc_opp=round(-l, 4),
        dd_you=0.0, dd_opp=0.0,
        end_prob=1 - delta,
    )


def make_round_prompt(history: list[tuple[int, int]], round_num: int) -> str:
    if not history:
        return "This is round 1. What do you choose?"
    lines = []
    for t, (my_act, opp_act) in enumerate(history, 1):
        my_s = "Cooperate" if my_act == 1 else "Defect"
        opp_s = "Cooperate" if opp_act == 1 else "Defect"
        lines.append(f"Round {t}: You chose {my_s}, opponent chose {opp_s}")
    lines.append(f"\nThis is round {round_num}. What do you choose?")
    return "\n".join(lines)


PAYOFF = {
    (1, 1): lambda g, l: (1.0, 1.0),
    (1, 0): lambda g, l: (-l, 1 + g),
    (0, 1): lambda g, l: (1 + g, -l),
    (0, 0): lambda g, l: (0.0, 0.0),
}


def play_supergame(
    backend: LLMBackend,
    player_p1,
    player_p2,
    g: float,
    l: float,
    n_rounds: int,
    temperature: float,
    tracker: CostTracker,
) -> tuple[list[int], list[int], list[float], list[float]]:
    p1_hist: list[tuple[int, int]] = []
    p2_hist: list[tuple[int, int]] = []
    p1_actions, p2_actions = [], []
    p1_payoffs, p2_payoffs = [], []

    with ThreadPoolExecutor(max_workers=2) as pool:
        for t in range(n_rounds):
            rnd = t + 1
            prompt_p1 = make_round_prompt(p1_hist, rnd)
            prompt_p2 = make_round_prompt(p2_hist, rnd)

            fut1 = pool.submit(backend.query_action, player_p1, prompt_p1, temperature, tracker)
            fut2 = pool.submit(backend.query_action, player_p2, prompt_p2, temperature, tracker)
            a1 = fut1.result()
            a2 = fut2.result()

            pay1, pay2 = PAYOFF[(a1, a2)](g, l)

            p1_actions.append(a1)
            p2_actions.append(a2)
            p1_payoffs.append(pay1)
            p2_payoffs.append(pay2)

            p1_hist.append((a1, a2))
            p2_hist.append((a2, a1))

    return p1_actions, p2_actions, p1_payoffs, p2_payoffs


def draw_length(delta: float, rng: np.random.Generator, cap: int) -> int:
    return min(int(rng.geometric(p=1 - delta)), cap)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM vs LLM repeated prisoner's dilemma")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "experimental_data.csv")
    parser.add_argument("--model", type=str, default="gemini-2.0-flash",
                        help="P1 model (also P2 unless --model-p2 set)")
    parser.add_argument("--model-p2", type=str, default=None, help="P2 model; defaults to --model")
    parser.add_argument("--n-pairs", type=int, default=1, help="Number of independent LLM pairs")
    parser.add_argument("--n-supergames", type=int, default=10, help="Supergames per pair")
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cost-limit", type=float, default=25.0, help="Stop if estimated cost exceeds this (USD)")
    parser.add_argument("--outdir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "results" / "synthetic")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    model_p2_name = args.model_p2 or args.model
    rng = np.random.default_rng(args.seed)
    treatments = load_treatments(args.data)
    print(f"{len(treatments)} unique (g, l, delta) treatments loaded")

    backend_p1 = get_backend(args.model)
    backend_p2 = get_backend(model_p2_name) if model_p2_name != args.model else backend_p1

    inp_price, out_price = get_pricing(args.model)
    tracker = CostTracker(limit=args.cost_limit)
    tracker.set_pricing(inp_price, out_price)
    print(f"Backend: {'Gemini' if args.model.startswith('gemini') else 'OpenAI'} | "
          f"P1={args.model} P2={model_p2_name}")

    tag = args.model.replace("/", "_")
    if model_p2_name != args.model:
        tag += f"_vs_{model_p2_name.replace('/', '_')}"
    out_path = args.outdir / f"synthetic_{tag}_seed_{args.seed}.csv"

    rows = []
    stopped_early = False

    for pair_idx in range(args.n_pairs):
        if stopped_early:
            break
        session_id = pair_idx + 1
        p1_id = pair_idx * 2 + 1
        p2_id = pair_idx * 2 + 2

        for sg_idx in range(args.n_supergames):
            if tracker.exceeded:
                print(f"Cost limit ${args.cost_limit:.2f} reached (${tracker.cost:.2f} spent). "
                      f"Saving {len(rows)} rows collected so far.")
                stopped_early = True
                break

            t_idx = rng.integers(len(treatments))
            g = float(treatments.loc[t_idx, "g"])
            l_val = float(treatments.loc[t_idx, "l"])
            delta = float(treatments.loc[t_idx, "delta"])
            n_rounds = draw_length(delta, rng, args.max_rounds)

            sys_prompt = make_system_prompt(g, l_val, delta)
            player_p1 = backend_p1.create_player(args.model, sys_prompt)
            player_p2 = backend_p2.create_player(model_p2_name, sys_prompt)

            print(f"pair {session_id} sg {sg_idx + 1}/{args.n_supergames}: "
                  f"g={g:.3f} l={l_val:.3f} delta={delta:.2f} rounds={n_rounds} "
                  f"[${tracker.cost:.4f}]")

            p1_acts, p2_acts, p1_pays, p2_pays = play_supergame(
                backend_p1, player_p1, player_p2, g, l_val, n_rounds, args.temperature, tracker,
            )

            p1_enc = [1 if a else -1 for a in p1_acts]
            p2_enc = [1 if a else -1 for a in p2_acts]

            rows.append({
                "paper": f"synthetic_{args.model}",
                "id": p1_id, "session": session_id, "inter": sg_idx + 1,
                "c": json.dumps(p1_enc), "opp_c": json.dumps(p2_enc),
                "payoff": json.dumps(p1_pays),
                "delta": delta, "g": g, "l": l_val,
            })
            rows.append({
                "paper": f"synthetic_{model_p2_name}",
                "id": p2_id, "session": session_id, "inter": sg_idx + 1,
                "c": json.dumps(p2_enc), "opp_c": json.dumps(p1_enc),
                "payoff": json.dumps(p2_pays),
                "delta": delta, "g": g, "l": l_val,
            })

    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}")

    print(f"\nTotal: {tracker.input_tokens:,} input tokens, {tracker.output_tokens:,} output tokens, "
          f"${tracker.cost:.4f} estimated cost")


if __name__ == "__main__":
    main()
