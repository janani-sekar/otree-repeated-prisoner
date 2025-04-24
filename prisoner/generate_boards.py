import random
import json

def generate_boards(n_boards=1000, max_payoff=50):
    boards = []
    while len(boards) < n_boards:
        # draw four independent ints from 0…max_payoff
        T = random.randint(0, max_payoff)
        R = random.randint(0, max_payoff)
        P = random.randint(0, max_payoff)
        S = random.randint(0, max_payoff)
        # enforce strict ordering T > R > P > S
        if T > R > P > S:
            boards.append({
                "R": R,
                "S": S,
                "T": T,
                "P": P,
            })
    return boards

if __name__ == "__main__":
    bs = generate_boards(1000, 50)
    with open("gameboards.json", "w") as f:
        json.dump(bs, f, indent=2)
    print(f"Wrote {len(bs)} boards to gameboards.json")
