from otree.api import Bot
from . import pages
import random

class PlayerBot(Bot):
    def play_round(self):
        # Round 1: go through the onboarding flow
        if self.round_number == 1:
            yield pages.ReadyPage
            # Wait pages (ArrivalWaitPage, MatchStartWaitPage) are skipped by bots

        # Play decision round
        if self.round_number <= self.participant.vars['match_duration']:
            yield pages.Decision, {'decision': random.choice(['Cooperate', 'Defect'])}
            # Wait page (DecisionWaitPage) skipped automatically
            yield pages.EndRound
            if self.round_number < self.participant.vars['match_duration']:
                yield pages.RoundSyncWaitPage

        # End screen logic (final round)
        if self.round_number == self.participant.vars['match_duration']:
            yield pages.End
            yield pages.GeneralWaitPage
