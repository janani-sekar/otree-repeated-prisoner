from otree.api import Bot, Submission
from . import pages
import random

class PlayerBot(Bot):
    def play_round(self):
        # Round 1: onboarding page only
        if self.round_number == 1:
            yield pages.ReadyPage

        # Play if within match duration
        if self.round_number <= self.participant.vars['match_duration']:
            yield pages.Decision, {'decision': random.choice(['Cooperate', 'Defect'])}
            yield pages.EndRound

        # Final round: display end-of-game results
        if self.round_number == self.participant.vars['match_duration']:
            yield Submission(pages.End, check_html=False)
            # Do NOT yield GeneralWaitPage — it's a WaitPage
