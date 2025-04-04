from ._builtin import Page, WaitPage
from .models import Constants
import random

class GroupWaitPage(WaitPage):
    body_text = "Waiting for the other participant to join..."

class ReadyPage(Page):
    def is_displayed(self):
        return self.subsession.round_number == 1
    def vars_for_template(self):
        return {}

class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 90  # 1 minute 30 seconds total.
    
    def vars_for_template(self):
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
        return {'payoff_board': board}
    
    def before_next_page(self):
        # If no decision was made, mark a timeout.
        if not self.player.decision:
            self.player.timeout_occurred = True
            for p in self.group.get_players():
                p.participant.vars['match_ended'] = True

class TimeoutNotice(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        return {'timeout_message': "Either you or your opponent failed to make a decision on time, so the game ended early."}

class ResultsWaitPage(WaitPage):
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def after_all_players_arrive(self):
        for p in self.group.get_players():
            p.set_payoff()

class Results(Page):
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        opponent = self.player.other_player()
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
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        delta_value = self.subsession.session.vars['delta']
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        if current_round < actual_num_rounds:
            message = f"We rolled a die and the value was below {int(delta_value * 100)}, so the game continues."
            match_continues = True
            message_class = "alert alert-success"
        else:
            message = f"We rolled a die and the value was above {int(delta_value * 100)}, so the match has ended."
            match_continues = False
            message_class = "alert alert-danger"
        return {
            'delta_value': delta_value,
            'actual_num_rounds': actual_num_rounds,
            'current_round': current_round,
            'message': message,
            'message_class': message_class,
            'match_continues': match_continues
        }
    def before_next_page(self):
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        if current_round >= actual_num_rounds:
            self.participant.vars['match_ended'] = True

class End(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        return {'end_message': "Game ended."}

page_sequence = [
    GroupWaitPage,
    ReadyPage,
    Decision,
    TimeoutNotice,
    ResultsWaitPage,
    Results,
    EndRound,
    End
]
