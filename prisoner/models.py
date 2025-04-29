from otree.api import *
import os
import json
import pandas as pd
import random
from scipy.stats import geom

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
    num_rounds = int(geom(p=0.05).ppf(0.9))

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

    timed_out_rounds_json = models.LongStringField(initial="[]")

    # Real model fields so they show up in CSV export (saved only at final round)
    base_payment_cents = models.IntegerField(initial=0)
    bonus_payment_cents = models.IntegerField(initial=0)
    bonus_round = models.IntegerField(initial=0)
    total_payment_cents = models.IntegerField(initial=0)

    def other_player(self):
        return self.get_others_in_group()[0]

    def set_payoff(self):
        board = self.participant.vars.get('payoff_board', {})
        c_c = board.get('both_cooperate_payoff', 0)
        c_d = board.get('betrayed_payoff', 0)
        d_c = board.get('betray_payoff', 0)
        d_d = board.get('both_defect_payoff', 0)

        payoff_matrix = {
            'Cooperate': {'Cooperate': c_c, 'Defect': c_d},
            'Defect': {'Cooperate': d_c, 'Defect': d_d}
        }

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
        participant_vars = self.participant.vars
        is_final_round = self.round_number == participant_vars.get('match_duration', 0)

        return {
            'prolific_id': self.participant.label,
            'participant_code': self.participant.code,
            'round_number': self.round_number,
            'decision': self.decision,
            'timeout_occurred': self.timeout_occurred,
            'timed_out_rounds': self.timed_out_rounds_json,
            'payoff': self.payoff,
            'base_payment_cents': self.base_payment_cents if is_final_round else '',
            'bonus_payment_cents': self.bonus_payment_cents if is_final_round else '',
            'bonus_round': self.bonus_round if is_final_round else '',
            'total_payment_cents': self.total_payment_cents if is_final_round else '',
        }

def export_final_payments(session):

    final_round_number = session.config['match_duration']
    app_name = __name__.split('.')[0]  # e.g., if your app name is 'prisoner'
    players = session.get_participants()

    records = []
    for p in players:
        final_player = p.get_player_by_round(final_round_number)
        records.append({
            'participant_code': p.code,
            'prolific_id': p.label,
            'base_payment_cents': final_player.base_payment_cents,
            'bonus_payment_cents': final_player.bonus_payment_cents,
            'bonus_round': final_player.bonus_round,
            'total_payment_cents': final_player.total_payment_cents,
            'total_payment_usd': round((final_player.total_payment_cents / 100) * session.config['real_world_currency_per_point'], 2)
        })

    df = pd.DataFrame(records)
    output_path = f'_payment_exports/{session.code}_final_payments.csv'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)