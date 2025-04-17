from otree.api import *
import numpy as np
import random
from ._builtin import Page, WaitPage
from .models import Constants
from scipy.stats import geom

class ArrivalWaitPage(WaitPage):
    group_by_arrival_time = True

    def is_displayed(self):
        return self.round_number == 1

    def after_all_players_arrive(self):
        # 1) Choose delta and payoff board on the Group (for export)
        self.group.delta_value = random.choice([
            0.05, 0.10, 0.15, 0.20, 0.25,
            0.30, 0.35, 0.40, 0.45, 0.50,
            0.55, 0.60, 0.65, 0.70, 0.75,
            0.80, 0.85, 0.90, 0.95
        ])
        idx = random.randint(0, 9)
        self.group.game_payoff_cooperate_cooperate = Constants.both_cooperate_payoffs[idx]
        self.group.game_payoff_betrayed            = Constants.betrayed_payoffs[idx]
        self.group.game_payoff_betray              = Constants.betray_payoffs[idx]
        self.group.game_payoff_both_defect         = Constants.both_defect_payoffs[idx]

        # 2) Draw match duration once using geometric(delta)
        md = int(np.random.geometric(p=1 - self.group.delta_value))
        max_md = int(geom(p=0.05).ppf(0.9))
        if md > max_md:
            md = max_md
        self.group.match_duration = md

        # 3) Propagate everything into participant.vars
        for p in self.group.get_players():
            p.participant.vars['delta']           = self.group.delta_value
            p.participant.vars['match_duration']  = md
            p.participant.vars['payoff_board']    = {
                'both_cooperate_payoff': self.group.game_payoff_cooperate_cooperate,
                'betrayed_payoff':        self.group.game_payoff_betrayed,
                'betray_payoff':          self.group.game_payoff_betray,
                'both_defect_payoff':     self.group.game_payoff_both_defect,
            }
            p.participant.vars['timed_out'] = False


class ReadyPage(Page):
    def is_displayed(self):
        return self.round_number == 1

class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 60

    def vars_for_template(self):
        return {
            'delta':           self.player.participant.vars['delta'],
            'die_roll_value':  100-int(self.player.participant.vars['delta']*100),
            'match_duration':  self.player.participant.vars['match_duration'],
            'payoff_board':    self.player.participant.vars['payoff_board'],
            'round_number':    self.round_number,
        }

    def is_displayed(self):
        return (self.round_number <=
                self.player.participant.vars['match_duration'])

class DecisionWaitPage(WaitPage):
    body_text = "Waiting for the other participant to select a decision..."

    def is_displayed(self):
        return (self.round_number <=
                self.player.participant.vars['match_duration'])

    def after_all_players_arrive(self):
        # if anyone timed out (decision still None), end the match for both
        timed_out = any(not p.decision for p in self.group.get_players())
        if timed_out:
            for p in self.group.get_players():
                p.participant.vars['timed_out'] = True
                # truncate the match so we’ll go straight to End
                p.participant.vars['match_duration'] = self.round_number
            return
        # otherwise, compute payoffs as usual
        for p in self.group.get_players():
            p.set_payoff()

class TimeoutPage(Page):
    """Shown if either player missed the 90s timer."""
    def is_displayed(self):
        return self.player.participant.vars.get('timed_out', False)

class EndRound(Page):
    timeout_seconds = 30

    def vars_for_template(self):
        d1 = self.player.decision
        d2 = self.player.other_player().decision
        if d1 == 'Cooperate' and d2 == 'Cooperate':
            msg, cls = "Both cooperated!", "alert alert-success"
        elif d1 == 'Defect' and d2 == 'Defect':
            msg, cls = "Both defected!", "alert alert-danger"
        elif d1 == 'Cooperate' and d2 == 'Defect':
            msg, cls = "You cooperated while your partner defected.", "alert alert-warning"
        elif d1 == 'Defect' and d2 == 'Cooperate':
            msg, cls = "You defected while your partner cooperated.", "alert alert-info"
        else:
            msg, cls = "Round result pending.", "alert alert-secondary"

        md = self.player.participant.vars['match_duration']
        is_final = (self.round_number == md)

        return {
            'current_round':  self.round_number,
            'match_duration': md,
            'die_roll_value': 100 - int(self.player.participant.vars['delta'] * 100),
            'your_decision':  d1,
            'other_decision': d2,
            'round_payoff':   self.player.payoff,
            'message':        msg,
            'message_class':  cls,
            'is_final_round': is_final,
        }

    def is_displayed(self):
        timed_out = self.player.participant.vars.get('timed_out', False)
        md        = self.player.participant.vars['match_duration']
        return (not timed_out) and (self.round_number <= md)

class RoundSyncWaitPage(WaitPage):
    body_text = "Waiting for the other participant to finish reviewing the round results..."

    def is_displayed(self):
            timed_out = self.player.participant.vars.get('timed_out', False)
            md        = self.player.participant.vars['match_duration']
            return (not timed_out) and (self.round_number < md)

class End(Page):
    timeout_seconds = 30

    def vars_for_template(self):
        return {
            'current_round':   self.round_number,
            'match_duration':  self.player.participant.vars['match_duration'],
        }

    def is_displayed(self):
        return self.round_number == self.player.participant.vars['match_duration']

page_sequence = [
    ArrivalWaitPage,
    ReadyPage,
    Decision,
    DecisionWaitPage,
    TimeoutPage,
    EndRound,
    RoundSyncWaitPage,
    End,
]
