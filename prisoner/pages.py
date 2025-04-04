from ._builtin import Page, WaitPage
from .models import Constants
import random

class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 60
    timeout_submission = {'decision': 'Defect'}

    def vars_for_template(self):
        # Try to retrieve the payoff board from session vars.
        board = self.session.vars.get('payoff_board')
        if board is None:
            # If not defined, create it (this should normally run only in round 1)
            board_index = random.randint(0, 9)
            board = {
                'both_cooperate_payoff': Constants.both_cooperate_payoffs[board_index],
                'betrayed_payoff': Constants.betrayed_payoffs[board_index],
                'betray_payoff': Constants.betray_payoffs[board_index],
                'both_defect_payoff': Constants.both_defect_payoffs[board_index],
            }
            self.session.vars['payoff_board'] = board
        return {
            'payoff_board': board
        }

class ResultsWaitPage(WaitPage):
    def after_all_players_arrive(self):
        for p in self.group.get_players():
            p.set_payoff()

class Results(Page):
    def vars_for_template(self):
        opponent = self.player.other_player()
        # Ensure the payoff board exists
        board = self.session.vars.get('payoff_board')
        if board is None:
            board_index = random.randint(0, 9)
            board = {
                'both_cooperate_payoff': Constants.both_cooperate_payoffs[board_index],
                'betrayed_payoff': Constants.betrayed_payoffs[board_index],
                'betray_payoff': Constants.betray_payoffs[board_index],
                'both_defect_payoff': Constants.both_defect_payoffs[board_index],
            }
            self.session.vars['payoff_board'] = board

        return {
            'my_decision': self.player.decision,
            'opponent_decision': opponent.decision,
            'both_cooperate': self.player.decision == 'Cooperate' and opponent.decision == 'Cooperate',
            'both_defect': self.player.decision == 'Defect' and opponent.decision == 'Defect',
            'i_cooperate_he_defects': self.player.decision == 'Cooperate' and opponent.decision == 'Defect',
            'same_choice': self.player.decision == opponent.decision,
            'payoff_board': board
        }

class EndRound(Page):
    timeout_seconds = 30

    def vars_for_template(self):
        delta_value = self.subsession.session.vars['delta']
        continuation_chance = int(delta_value * 100)
        dieroll = self.group.roll_die()
        last_rounds = self.subsession.session.vars['last_rounds']
        current_round = self.subsession.round_number

        match_continues = (
            current_round not in last_rounds and 
            dieroll <= continuation_chance
        )

        return {
            'dieroll': dieroll,
            'continuation_chance': continuation_chance,
            'match_continues': match_continues,
            'is_last_round': current_round in last_rounds,
            'delta_value': delta_value
        }

    def before_next_page(self):
        delta_value = self.subsession.session.vars['delta']
        continuation_chance = int(delta_value * 100)
        if (self.group.dieroll > continuation_chance or 
            self.subsession.round_number in self.subsession.session.vars['last_rounds']):
            self.participant.vars['match_ended'] = True

class End(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)

page_sequence = [
    Decision,
    ResultsWaitPage,
    Results,
    EndRound,
    End
]
