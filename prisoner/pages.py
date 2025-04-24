from otree.api import *
import numpy as np
import random
from ._builtin import Page, WaitPage
import json
from .models import Constants, pregen_boards
from scipy.stats import geom

class ArrivalWaitPage(WaitPage):
    group_by_arrival_time = True

    def is_displayed(self):
        return self.round_number == 1

    def after_all_players_arrive(self):
        self.group.delta_value = random.choice([
            0.05, 0.10, 0.15, 0.20, 0.25,
            0.30, 0.35, 0.40, 0.45, 0.50,
            0.55, 0.60, 0.65, 0.70, 0.75,
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
            p.participant.vars['delta'] = self.group.delta_value
            p.participant.vars['match_duration'] = self.group.match_duration
            p.participant.vars['payoff_board'] = {
                'both_cooperate_payoff': self.group.game_payoff_cooperate_cooperate,
                'betrayed_payoff': self.group.game_payoff_betrayed,
                'betray_payoff': self.group.game_payoff_betray,
                'both_defect_payoff': self.group.game_payoff_both_defect,
            }

class ReadyPage(Page):
    def is_displayed(self):
        return self.round_number == 1
    
class MatchStartWaitPage(WaitPage):
    body_text = "Waiting for the other participant to be ready..."

    def is_displayed(self):
        return self.round_number == 1

class Decision(Page):
    form_model = 'player'
    form_fields = ['decision']
    timeout_seconds = 60

    def timer_text(self):
        return "Time left to make your decision for this round:"

    def is_displayed(self):
        return self.round_number <= self.player.participant.vars['match_duration']

    def before_next_page(self):
        if self.timeout_happened:
            self.player.timeout_occurred = True
            self.player.decision = random.choice(['Cooperate', 'Defect'])

            # Properly append to the full timeout history
            try:
                current_list = json.loads(self.player.timed_out_rounds_json)
                if not isinstance(current_list, list):
                    current_list = []
            except (json.JSONDecodeError, TypeError):
                current_list = []

            if self.round_number not in current_list:
                current_list.append(self.round_number)

            self.player.timed_out_rounds_json = json.dumps(current_list)


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
                # Assign random decision
                p.timeout_occurred = True
                p.decision = random.choice(['Cooperate', 'Defect'])

                # Append to timeout list (safely handles existing history)
                try:
                    current_list = json.loads(p.timed_out_rounds_json)
                    if not isinstance(current_list, list):
                        current_list = []
                except (json.JSONDecodeError, TypeError):
                    current_list = []

                if p.round_number not in current_list:
                    current_list.append(p.round_number)

                p.timed_out_rounds_json = json.dumps(current_list)

        for p in self.group.get_players():
            p.set_payoff()


class EndRound(Page):
    timeout_seconds = 30

    def timer_text(self):
        return "Time left to view this round's results:"

    def vars_for_template(self):
        d1 = self.player.decision
        d2 = self.player.other_player().decision
        
        return {
            'current_round': self.round_number,
            'timed_out_this_round': self.player.timeout_occurred,
            'match_duration': self.player.participant.vars['match_duration'],
            'die_roll_value': int(self.player.participant.vars['delta'] * 100),
            'payoff_board': self.player.participant.vars['payoff_board'],
            'you': d1,
            'other': d2,
            'round_payoff': self.player.payoff,
            'is_final_round': self.round_number == self.player.participant.vars['match_duration'],
        }

    def is_displayed(self):
        return self.round_number <= self.player.participant.vars['match_duration']

class RoundSyncWaitPage(WaitPage):
    body_text = "Waiting for the other participant to finish reviewing the round results..."

    def is_displayed(self):
        return self.round_number < self.player.participant.vars['match_duration']

class End(Page):
    timeout_seconds = 30

    def vars_for_template(self):
        return {
            'current_round': self.round_number,
            'match_duration': self.player.participant.vars['match_duration'],
        }

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
]
