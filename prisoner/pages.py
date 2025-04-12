from ._builtin import Page, WaitPage
from .models import Constants
import random

# -------------------------------------------------------------------
# GroupWaitPage: Only used in round 1, to let participants join the session.
# -------------------------------------------------------------------
class GroupWaitPage(WaitPage):
    body_text = "Waiting for another participant to join the game..."
    group_by_arrival_time = True
    
    def is_displayed(self):
        # Show this wait page ONLY in round 1.
        return self.subsession.round_number == 1

# -------------------------------------------------------------------
# ReadyPage: shown only in round 1, also extracts the Prolific ID.
# -------------------------------------------------------------------
class ReadyPage(Page):
    timeout_seconds = 30
    def is_displayed(self):
        return self.subsession.round_number == 1
    def vars_for_template(self):
        return {}
    def before_next_page(self, timeout_happened=False):
        self.player.prolific_id = self.participant.label

# -------------------------------------------------------------------
# DecisionSyncPage: Wait page to ensure both players click "Next" at start.
# If you only want it in round 1, add an is_displayed method here too.
# -------------------------------------------------------------------
class DecisionSyncPage(WaitPage):
    body_text = "Waiting for both participants to click next. Page will autoadvance in 30 seconds."

    # If you want this only in round 1, uncomment this:
    # def is_displayed(self):
    #     return self.subsession.round_number == 1

# -------------------------------------------------------------------
# Decision Page: 90-second timer with an inline warning after 30s.
# -------------------------------------------------------------------
class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 90
    
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
            game_matrix = {
                'Cooperate': {
                    'Cooperate': {'self': board['both_cooperate_payoff'], 'other': board['both_cooperate_payoff']},
                    'Defect':    {'self': board['betrayed_payoff'],       'other': board['betray_payoff']}
                },
                'Defect': {
                    'Cooperate': {'self': board['betray_payoff'],         'other': board['betrayed_payoff']},
                    'Defect':    {'self': board['both_defect_payoff'],    'other': board['both_defect_payoff']}
                }
            }
            self.session.vars['game_matrix'] = game_matrix
        return {'payoff_board': board}

    def before_next_page(self):
        if not self.player.decision:
            self.player.timeout_occurred = True
            for p in self.group.get_players():
                p.participant.vars['match_ended'] = True

# -------------------------------------------------------------------
# TimeoutNotice Page: if a player timed out on the Decision page.
# -------------------------------------------------------------------
class TimeoutNotice(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        return {'timeout_message': "Either you or your opponent failed to make a decision on time, so the game ended early."}

# -------------------------------------------------------------------
# ResultsWaitPage: Wait page for payoff calculation.
# -------------------------------------------------------------------
class ResultsWaitPage(WaitPage):
    body_text = "Waiting for the other participant to make a decision."
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def after_all_players_arrive(self):
        for p in self.group.get_players():
            p.set_payoff()

# -------------------------------------------------------------------
# Results Page: displays outcomes; auto-advances after 30 seconds.
# -------------------------------------------------------------------
class Results(Page):
    timeout_seconds = 30
    def is_displayed(self):
        return not self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        opponent = self.player.other_player()
        board = self.session.vars.get('payoff_board')
        if board is None:
            board_index = random.randint(0, 9)
            board = {
                'both_cooperate_payoff': Constants.both_cooperate_payoffs[board_index],
                'betrayed_payoff':       Constants.betrayed_payoffs[board_index],
                'betray_payoff':         Constants.betray_payoffs[board_index],
                'both_defect_payoff':    Constants.both_defect_payoffs[board_index],
            }
            self.session.vars['payoff_board'] = board

        return {
            'my_decision': self.player.decision,
            'opponent_decision': opponent.decision,
            'both_cooperate': self.player.decision == 'Cooperate' and opponent.decision == 'Cooperate',
            'both_defect':    self.player.decision == 'Defect' and opponent.decision == 'Defect',
            'i_cooperate_he_defects': self.player.decision == 'Cooperate' and opponent.decision == 'Defect',
            'same_choice': self.player.decision == opponent.decision,
            'payoff_board': board,
            'next_button_auto': 30
        }

# -------------------------------------------------------------------
# EndRound Page: static message based on the precomputed match length; auto-advance after 30s.
# -------------------------------------------------------------------
class EndRound(Page):
    timeout_seconds = 30
    def vars_for_template(self):
        delta_value = self.subsession.session.vars['delta']
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        threshold = (1 - delta_value) * 100
        if current_round < actual_num_rounds:
            message = f"We simulated a die roll and the value was greater than {threshold:.0f}, so the game continues."
            message_class = "alert alert-success"
        else:
            message = f"We simulated a die roll and the value was less than or equal to {threshold:.0f}, so the match has ended."
            message_class = "alert alert-danger"
        return {
            'delta_value':       delta_value,
            'actual_num_rounds': actual_num_rounds,
            'current_round':     current_round,
            'message':           message,
            'message_class':     message_class,
            'next_button_auto':  30
        }
    def before_next_page(self):
        actual_num_rounds = self.subsession.session.vars['actual_num_rounds']
        current_round = self.subsession.round_number
        if current_round >= actual_num_rounds:
            self.participant.vars['match_ended'] = True

# -------------------------------------------------------------------
# RoundFinishWaitPage: wait page after EndRound in subsequent rounds.
# -------------------------------------------------------------------
class RoundFinishWaitPage(WaitPage):
    body_text = "Waiting for the other participant to finish viewing results from the round..."
    def is_displayed(self):
        # Only appear for rounds beyond the first, if you want a separate message from GroupWaitPage.
        return self.subsession.round_number > 1

# -------------------------------------------------------------------
# End Page: final static end screen.
# -------------------------------------------------------------------
class End(Page):
    def is_displayed(self):
        return self.participant.vars.get('match_ended', False)
    def vars_for_template(self):
        return {'end_message': "Game ended."}

# -------------------------------------------------------------------
# Page Sequence
# -------------------------------------------------------------------
page_sequence = [
    GroupWaitPage,       # Only round 1
    ReadyPage,           # Only round 1
    DecisionSyncPage,    # Shown each round by default; comment out is_displayed if you only want round 1
    Decision,
    TimeoutNotice,
    ResultsWaitPage,
    Results,
    EndRound,
    RoundFinishWaitPage, # Shown in subsequent rounds if one player finishes EndRound early
    End
]
