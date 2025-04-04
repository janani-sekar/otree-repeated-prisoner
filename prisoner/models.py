from otree.api import *
import numpy as np
import random
import time

doc = """
Repeated Prisoner's Dilemma with random continuation.
The continuation probability (delta) is sampled from [0.1, 0.2, …, 0.9].
A fixed payoff board is chosen at the start.
There are 10 possible boards; the board is determined by selecting the same index from 4 payoff lists.
"""

class Constants(BaseConstants):
    name_in_url = 'prisoner'
    players_per_group = 2
    num_rounds = 100  # placeholder; actual rounds come from session vars
    num_matches = 1

    # Lists for the 10 possible boards (index 0 to 9)
    both_cooperate_payoffs = [28, 30, 32, 34, 36, 38, 40, 42, 44, 46]
    betrayed_payoffs = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26]
    betray_payoffs = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58]
    both_defect_payoffs = [18, 20, 22, 24, 26, 28, 30, 32, 34, 36]

    time_limit_seconds = 3600


class Subsession(BaseSubsession):
    delta_value = models.FloatField(null=True)
    match_number = models.IntegerField()
    round_in_match = models.IntegerField()
    # New field: store total predetermined rounds in the database.
    total_rounds = models.IntegerField()

    def creating_session(self):
        if self.round_number == 1:
            delta_value = random.choice([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
            self.session.vars['delta'] = delta_value
            self.delta_value = delta_value

            board_index = random.randint(0, 9)
            payoff_board = {
                'both_cooperate_payoff': Constants.both_cooperate_payoffs[board_index],
                'betrayed_payoff': Constants.betrayed_payoffs[board_index],
                'betray_payoff': Constants.betray_payoffs[board_index],
                'both_defect_payoff': Constants.both_defect_payoffs[board_index],
            }
            self.session.vars['payoff_board'] = payoff_board

            match_duration = np.random.geometric(p=1 - delta_value, size=Constants.num_matches).tolist()
            last_rounds = np.cumsum(match_duration).tolist()
            first_rounds = [1] + [last_rounds[k - 1] + 1 for k in range(1, len(match_duration))]

            actual_num_rounds = int(last_rounds[-1])
            self.session.vars.update({
                'match_duration': match_duration,
                'last_rounds': last_rounds,
                'first_rounds': first_rounds,
                'actual_num_rounds': actual_num_rounds,
                'start_time': time.time(),
                'alive': True
            })
            self.total_rounds = actual_num_rounds
        else:
            self.delta_value = self.session.vars['delta']

        if self.round_number > self.session.vars['actual_num_rounds']:
            self.match_number = 0
            self.round_in_match = 0
            return

        for k, last_round in enumerate(self.session.vars['last_rounds'], start=1):
            if self.round_number <= last_round:
                self.match_number = k
                break

        self.round_in_match = (self.round_number - self.session.vars['first_rounds'][self.match_number - 1] + 1)

        if self.round_number in self.session.vars['first_rounds']:
            self.group_randomly()
        else:
            self.group_like_round(self.round_number - 1)


class Group(BaseGroup):
    dieroll = models.IntegerField(initial=-1)
    def roll_die(self):
        if self.dieroll == -1:
            self.dieroll = random.randint(1, 100)
        return self.dieroll


class Player(BasePlayer):
    decision = models.StringField(
        choices=[['Cooperate', 'Cooperate'], ['Defect', 'Defect']],
        widget=widgets.RadioSelect,
        label="Your decision:"
    )
    # New field: record if a timeout occurred.
    timeout_occurred = models.BooleanField(initial=False)

    def other_player(self):
        return self.get_others_in_group()[0]

    def set_payoff(self):
        # If either player did not decide, assign 0.
        if self.decision == "" or self.other_player().decision == "":
            self.payoff = 0
            return

        board = self.session.vars['payoff_board']
        payoff_matrix = {
            'Cooperate': {
                'Cooperate': board['both_cooperate_payoff'],
                'Defect': board['betrayed_payoff']
            },
            'Defect': {
                'Cooperate': board['betray_payoff'],
                'Defect': board['both_defect_payoff']
            }
        }
        self.payoff = payoff_matrix[self.decision][self.other_player().decision]
