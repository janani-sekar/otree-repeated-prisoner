from locust import HttpUser, task, between
import random

class ProlificUser(HttpUser):
    wait_time = between(1, 3)  # simulate natural delays between requests

    @task
    def join_room(self):
        # Simulate a unique participant_label
        label = f"P{random.randint(1, 250):03}"
        self.client.get(f"/room/Prolific_1/?participant_label={label}", name="/room/Prolific_1/")