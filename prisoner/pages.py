from ._builtin import Page, WaitPage
from .models import Constants
import random

# Wait page with static message when players first join.
class GroupWaitPage(WaitPage):
    body_text = "Waiting for the other participant to click next..."

# READY PAGE: only shown in round 1. This page now extracts the Prolific ID.
class ReadyPage(Page):
    timeout_seconds = 30
    def is_displayed(self):
        return self.subsession.round_number == 1
    def vars_for_template(self):
        return {}
    def before_next_page(self, timeout_happened=False):
        # Extract the Prolific ID from participant.label and store it in the player's prolific_id field.
        self.player.prolific_id = self.participant.label

# DECISION SYNC PAGE: static wait page to synchronize the start of the Decision page.
class DecisionSyncPage(WaitPage):
    body_text = "Both participants are ready. Please wait while we synchronize..."

# DECISION PAGE: 90-second timer with an inline danger-style warning (displayed above the payoff matrix) after 30 seconds.
class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 90  # Total of 1 minute 30 seconds.
    # No timeout_submission used.
    
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
            # Also store the full game matrix in session (for runtime use if needed)
            game_matrix = {
                'Cooperate': {
                    'Cooperate': {'self': board['both_cooperate_payoff'],
                                   'other': board['both_cooperate_payoff']},
                    'Defect':    {'self': board['betrayed_payoff'],
                                   'other': board['betray_payoff']}
                },
                'Defect': {
                    'Cooperate': {'self': board['betray_payoff'],
                                   'other': board['betrayed_payoff']},
                    'Defect':    {'self': board['both_defect_payoff'],
                                   'other': board['both_defect_payoff']}
                }
            }
            self.session.vars['game_matrix'] = game_matrix
        return {'payoff_board': board}
    
    def before_next_page(self):
        # If no decision was made (i.e. decision is falsy), mark a timeout and end the match for everyone.
        if not self.player.decision:
            self.player.timeout_occurred = True
            for p in self.group.get_players():
                p.participant.vars['match_ended'] = True

# TIMEOUT NOTICE PAGE: shown if a timeout occurred on the Decision page.
class TimeoutNotice(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        return {'timeout_message': "Either you or your opponent failed to make a decision on time, so the game ended early."}

# RESULTS WAIT PAGE: static wait page that says "Waiting for the other participant to make a decision."
class ResultsWaitPage(WaitPage):
    body_text = "Waiting for the other participant to make a decision."
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def after_all_players_arrive(self):
        for p in self.group.get_players():
            p.set_payoff()

# RESULTS PAGE: displays outcomes; auto-advances after 30 seconds.
class Results(Page):
    timeout_seconds = 30  # Auto-advance after 30 seconds.
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
            'payoff_board': board,
            'next_button_auto': self.next_button_auto if hasattr(self, 'next_button_auto') else 30
        }

# END ROUND PAGE: displays a static message based on the precomputed match length; auto-advances after 30 seconds.
class EndRound(Page):
    timeout_seconds = 30  # Auto-advance after 30 seconds.
    def vars_for_template(self):
        delta_value = self.subsession.session.vars['delta']
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        threshold = (1 - delta_value) * 100  # (1-delta)*100 used as threshold.
        if current_round < actual_num_rounds:
            message = f"We simulated a die roll and the value was greater than {threshold:.0f}, so the game continues."
            message_class = "alert alert-success"
        else:
            message = f"We simulated a die roll and the value was less than or equal to {threshold:.0f}, so the match has ended."
            message_class = "alert alert-danger"
        return {
            'delta_value': delta_value,
            'actual_num_rounds': actual_num_rounds,
            'current_round': current_round,
            'message': message,
            'message_class': message_class,
            'next_button_auto': self.next_button_auto if hasattr(self, 'next_button_auto') else 30
        }
    def before_next_page(self):
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        if current_round >= actual_num_rounds:
            self.participant.vars['match_ended'] = True

# END PAGE: final static end screen.
class End(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    
    @staticmethod              
    def js_vars(player):
        return dict(
            completionlink=
              player.subsession.session.config['completionlink']
        )
    
    def vars_for_template(self):
        return {'end_message': "Game ended."}

# PAGE SEQUENCE
page_sequence = [
    GroupWaitPage,
    ReadyPage,          # Now extracts Prolific ID in before_next_page.
    DecisionSyncPage,   # Synchronizes the start of the Decision page.
    Decision,
    TimeoutNotice,
    ResultsWaitPage,
    Results,
    EndRound,
    End
]

# DECISION SYNC PAGE: ensures both players click "Next" so that the Decision page timer starts simultaneously.
class DecisionSyncPage(WaitPage):
    body_text = "Both participants are ready. Please wait while we synchronize..."
