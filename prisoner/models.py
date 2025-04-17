from otree.api import *
import random

doc = """
Repeated Prisoner's Dilemma where each pair is fixed for the entire session.
Each pair (group) is assigned its own continuation probability (delta),
match duration and payoff board in round 1, which remain unchanged throughout the session.
Players are paired by their arrival time via an asynchronous Wait Page.
"""

class Constants(BaseConstants):
    name_in_url = 'prisoner'
    players_per_group = 2
    num_rounds = 100
    time_limit_seconds = 3600

    # Payoff lists for 10 possible boards (indices 0 to 9)
    both_cooperate_payoffs = [28, 30, 32, 34, 36, 38, 40, 42, 44, 46]
    betrayed_payoffs        = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26]
    betray_payoffs          = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58]
    both_defect_payoffs     = [18, 20, 22, 24, 26, 28, 30, 32, 34, 36]


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
