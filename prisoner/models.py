from otree.api import *
import os
import json
import random

doc = """
Repeated Prisoner's Dilemma where each pair is fixed for the entire session.
Each pair (group) is assigned its own continuation probability (delta),
match duration and payoff board in round 1, which remain unchanged throughout the session.
Players are paired by their arrival time via an asynchronous Wait Page.
"""

# load the pre‑generated boards
board_path = os.path.join(os.path.dirname(__file__), "gameboards.json")
with open(board_path) as f:
    pregen_boards = json.load(f)

class Constants(BaseConstants):
    name_in_url = 'prisoner'
    players_per_group = 2
    num_rounds = 100
    time_limit_seconds = 3600

class Subsession(BaseSubsession):
    def creating_session(self):
        if self.round_number > 1:
            self.group_like_round(1)

class Group(BaseGroup):
    dieroll = models.IntegerField(initial=-1)

    # Stored in round 1 (for data export), but not used at runtime
    delta_value                      = models.FloatField(null=True)
    match_duration                   = models.IntegerField(null=True)
    game_payoff_cooperate_cooperate  = models.IntegerField(null=True)
    game_payoff_betrayed             = models.IntegerField(null=True)
    game_payoff_betray               = models.IntegerField(null=True)
    game_payoff_both_defect          = models.IntegerField(null=True)

    def roll_die(self):
        if self.dieroll == -1:
            self.dieroll = random.randint(1, 100)
        return self.dieroll


class Player(BasePlayer):
    prolific_id = models.StringField(initial="")

    decision = models.StringField(
        choices=[['Cooperate', 'Cooperate'], ['Defect', 'Defect']],
        widget=widgets.RadioSelect,
        label="Your decision:"
    )
    timeout_occurred = models.BooleanField(initial=False)
    
    # always start as an empty JSON list rather than null
    timed_out_rounds_json = models.LongStringField(initial="[]")


    def other_player(self):
        return self.get_others_in_group()[0]

    def set_payoff(self):
        # Pull the board from participant.vars (set in ArrivalWaitPage)
        board = self.participant.vars.get('payoff_board', {})
        # If for some reason it's missing, default all payoffs to zero
        c_c = board.get('both_cooperate_payoff', 0)
        c_d = board.get('betrayed_payoff', 0)
        d_c = board.get('betray_payoff', 0)
        d_d = board.get('both_defect_payoff', 0)

        # Build payoff matrix
        payoff_matrix = {
            'Cooperate': {
                'Cooperate': c_c,
                'Defect':    c_d
            },
            'Defect': {
                'Cooperate': d_c,
                'Defect':    d_d
            }
        }

        # If either decision is missing, treat payoff as 0
        if not self.decision or not self.other_player().decision:
            self.payoff = 0
        else:
            self.payoff = payoff_matrix[self.decision][self.other_player().decision]

    def decision_was_random(self):
        try:
            rounds = json.loads(self.timed_out_rounds_json or "[]")
        except Exception:
            return False
        return self.round_number in rounds

    def vars_for_export(self):
        return {
            "round_number": self.round_number,
            "decision": self.decision,
            "timeout_occurred": self.timeout_occurred,
            "timed_out_rounds_json": self.timed_out_rounds_json,
            "decision_was_random": self.decision_was_random()
        }