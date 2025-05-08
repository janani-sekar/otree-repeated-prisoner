import random
import json
import pandas as pd

random.seed(0)
def generate_boards(n_boards=1000, max_payoff=25):
    boards = []
    while len(boards) < n_boards:
        # draw four independent ints from 1…max_payoff
        T = random.randint(1, max_payoff)
        R = random.randint(1, max_payoff)
        P = random.randint(1, max_payoff)
        S = random.randint(1, max_payoff)
        # enforce strict ordering T > R > P > S
        if T > R > P > S:
            if 2 * R > (T + S):
                boards.append({
                    "R": R,
                    "S": S,
                    "T": T,
                    "P": P,
                })
    return boards

if __name__ == "__main__":
    bs = generate_boards(2000, 25)
    with open("./prisoner/gameboards.json", "w") as f:
        json.dump(bs, f, indent=2)
    print(f"Wrote {len(bs)} boards to gameboards.json")

    bs = pd.DataFrame(bs)
    l = -1 * ((bs['S']-bs['P'])/(bs['R'] - bs['P']))
    print("Mean l:", l.mean())
    print("Median l:", l.median())
    print("Min l:", l.min())
    print("Max l:", l.max())
    print("1st quartile l:", l.quantile(0.25))
    print("3rd quartile l:", l.quantile(0.75))
    print("95th percentile l:", l.quantile(0.95))

    g = ((bs['T'] - bs['P'])/(bs['R'] - bs['P'])) - 1
    print("Mean g:", g.mean())
    print("Median g:", g.median())
    print("Min g:", g.min())
    print("Max g:", g.max())
    print("1st quartile g:", g.quantile(0.25))
    print("3rd quartile g:", g.quantile(0.75))
    print("95th percentile g:", g.quantile(0.95))

