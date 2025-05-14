from otree.api import *
import numpy as np
import random
from ._builtin import Page, WaitPage
import json
from .models import Constants, pregen_boards
from scipy.stats import geom

class ArrivalWaitPage(WaitPage):
    body_text = "Waiting for another participant to join. Please do not exit this page..."
    group_by_arrival_time = True
    
    def is_displayed(self):
        return self.round_number == 1
    
    def after_all_players_arrive(self):
        self.group.delta_value = random.choice([
            0.50, 0.55, 0.60, 0.65, 0.70, 0.75,
            0.80, 0.85, 0.90, 0.95
        ])
        board = random.choice(pregen_boards)
        self.group.game_payoff_cooperate_cooperate = board['R']
        self.group.game_payoff_betrayed = board['S']
        self.group.game_payoff_betray = board['T']
        self.group.game_payoff_both_defect = board['P']

        md = int(np.random.geometric(p=1 - self.group.delta_value))
        max_md = int(geom(p=0.05).ppf(0.9))
        self.group.match_duration = min(md, max_md)

        for p in self.group.get_players():

            if not p.prolific_id:
                p.prolific_id = p.participant.label or ""

            if not p.participant.label:
                p.participant.label = p.prolific_id  # Just in case

            p.participant.vars['delta'] = self.group.delta_value
            p.participant.vars['match_duration'] = self.group.match_duration
            p.participant.vars['payoff_board'] = {
                'both_cooperate_payoff': self.group.game_payoff_cooperate_cooperate,
                'betrayed_payoff': self.group.game_payoff_betrayed,
                'betray_payoff': self.group.game_payoff_betray,
                'both_defect_payoff': self.group.game_payoff_both_defect,
            }

class ReadyPage(Page):
    timeout_seconds = 60

    def timer_text(self):
        return "Time left until the game automatically begins:"

    def is_displayed(self):
        return self.round_number == 1
    
class MatchStartWaitPage(WaitPage):
    body_text = "Waiting for the other participant to be ready..."

    def is_displayed(self):
        return self.round_number == 1

class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 30

    def timer_text(self):
        return "Time left to make your decision for this round:"

    def is_displayed(self):
        return self.round_number <= self.player.participant.vars['match_duration']

    def before_next_page(self):
        
        if self.round_number > 1:
            g  = self.group
            g1 = self.player.in_round(1).group
            # only copy once when blank
            if g.field_maybe_none('delta_value') is None:
                g.delta_value                     = g1.delta_value
                g.match_duration                  = g1.match_duration
                g.game_payoff_cooperate_cooperate = g1.game_payoff_cooperate_cooperate
                g.game_payoff_betrayed            = g1.game_payoff_betrayed
                g.game_payoff_betray              = g1.game_payoff_betray
                g.game_payoff_both_defect         = g1.game_payoff_both_defect
                # optional debug
                print(f"[ROUND {self.round_number}] Group settings copied from round 1")

        # pull the list (might be empty)
        rounds = self.player.participant.vars.get('timed_out_rounds', [])
        # write it into the per-round field so exports pick it up
        self.player.timed_out_rounds_json = json.dumps(rounds)

        if self.timeout_happened:
            self.player.timeout_occurred = True
            self.player.decision = random.choice(['Cooperate', 'Defect'])
            # update the participant.vars list
            if self.round_number not in rounds:
                rounds.append(self.round_number)
                self.player.participant.vars['timed_out_rounds'] = rounds
            # mirror again
            self.player.timed_out_rounds_json = json.dumps(rounds)

    def vars_for_template(self):
        return {
            "round_number": self.round_number,
            "match_duration": self.player.participant.vars['match_duration'],
            "die_roll_value": int(self.player.participant.vars['delta'] * 100),
            'payoff_board': self.player.participant.vars['payoff_board'],
        }

class DecisionWaitPage(WaitPage):
    body_text = "Waiting for the other participant to select a decision..."

    def is_displayed(self):
        return self.round_number <= self.player.participant.vars['match_duration']

    def after_all_players_arrive(self):
        for p in self.group.get_players():
            if p.decision is None:
                rounds = p.participant.vars.get('timed_out_rounds', [])
                if p.round_number not in rounds:
                    rounds.append(p.round_number)
                p.participant.vars['timed_out_rounds'] = rounds
                p.timed_out_rounds_json = json.dumps(rounds)   # ← mirror again
                p.timeout_occurred = True
                p.decision = random.choice(['Cooperate', 'Defect'])

            p.set_payoff()
            # Record payoff for this round
            if 'payoffs_per_round' not in p.participant.vars:
                p.participant.vars['payoffs_per_round'] = []

            p.participant.vars['payoffs_per_round'].append(p.payoff)


class EndRound(Page):
    timeout_seconds = 30

    def timer_text(self):
        return "Time left to view this round's results:"

    def vars_for_template(self):
        return {
            'current_round':          self.round_number,
            'timed_out_this_round':   self.player.timeout_occurred,
            'match_duration':         self.player.participant.vars['match_duration'],
            'die_roll_value':         int(self.player.participant.vars['delta'] * 100),
            'payoff_board':           self.player.participant.vars['payoff_board'],
            'you':                    self.player.decision,
            'other':                  self.player.other_player().decision,
            'round_payoff':           self.player.payoff,
            'is_final_round':         self.round_number == self.player.participant.vars['match_duration'],
        }


    def is_displayed(self):
        return self.round_number <= self.player.participant.vars['match_duration']

class RoundSyncWaitPage(WaitPage):
    body_text = "Waiting for the other participant to finish reviewing the round results..."

    def is_displayed(self):
        return self.round_number < self.player.participant.vars['match_duration']

class End(Page):
    form_model = 'player'
    form_fields = []

    def is_displayed(self):
        match_duration = self.player.participant.vars.get('match_duration', 0)
        return self.round_number == match_duration

    def vars_for_template(self):
        participant_vars = self.player.participant.vars
        rounds_played = participant_vars.get('match_duration', 0)
        conversion_rate = self.session.config['real_world_currency_per_point']

        if not participant_vars.get('payment_computed'):
            base_payment_cents = 100
            adjustment_cents = 0

            if rounds_played > 10:
                adjustment_cents = min(rounds_played-10, 10) * 10
                base_payment_cents += adjustment_cents

            bonus_round = rounds_played 
            payoffs = participant_vars.get('payoffs_per_round', [])
            bonus_payment_cents = int(payoffs[bonus_round - 1] if bonus_round and bonus_round - 1 < len(payoffs) else 0)
            total_payment_cents = base_payment_cents + bonus_payment_cents

            participant_vars['base_payment_cents'] = base_payment_cents
            participant_vars['bonus_payment_cents'] = bonus_payment_cents
            participant_vars['bonus_round'] = bonus_round
            participant_vars['total_payment_cents'] = total_payment_cents
            participant_vars['payment_computed'] = True

            # Save participant.payoff for oTree
            self.participant.payoff = cu(total_payment_cents)

        self.player.base_payment_cents = participant_vars.get('base_payment_cents', 0)
        self.player.bonus_payment_cents = participant_vars.get('bonus_payment_cents', 0)
        self.player.bonus_round = participant_vars.get('bonus_round', 0)
        self.player.total_payment_cents = participant_vars.get('total_payment_cents', 0)

        base_cents = participant_vars.get('base_payment_cents', 0)
        bonus_cents = participant_vars.get('bonus_payment_cents', 0)
        bonus_round = participant_vars.get('bonus_round', 0)

        base_payment = f"${base_cents * conversion_rate:.2f}"
        bonus_payment = f"${bonus_cents * conversion_rate:.2f}"
        total_payment = f"${(base_cents + bonus_cents) * conversion_rate:.2f}"

        return {
            'rounds_played': int(rounds_played),
            'base_payment': base_payment,
            'bonus_round': bonus_round,
            'bonus_payment': bonus_payment,
            'total_payment': total_payment,
        }

class GeneralWaitPage(WaitPage):
    body_text = "Game is over..."

    def is_displayed(self):
        return self.round_number == self.player.participant.vars['match_duration']


page_sequence = [
    ArrivalWaitPage,
    ReadyPage,
    MatchStartWaitPage,
    Decision,
    DecisionWaitPage,
    EndRound,
    RoundSyncWaitPage,
    End,
    GeneralWaitPage,
]
