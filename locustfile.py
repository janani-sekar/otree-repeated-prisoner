from locust import HttpUser, task, between
import random
from bs4 import BeautifulSoup  # you need to install this or parse manually

class ProlificUser(HttpUser):
    session_code = "gvryqebq"
    app_name = "prisoner"
    room_name = "Prolific_1"
    wait_time = between(0.5, 1.5)

    label_pool = [f"P{i:03}" for i in range(1, 501)]

    def on_start(self):
        if ProlificUser.label_pool:
            self.label = ProlificUser.label_pool.pop()
        else:
            self.label = f"PX{random.randint(1000, 9999)}"
        print(f"[START] Simulating participant {self.label}")

    @task
    def simulate_entry_and_flow(self):
        # Step 1: Enter the room
        resp = self.client.get(
            f"/room/{self.room_name}/?participant_label={self.label}",
            name="/room_entry",
            allow_redirects=True
        )
        # print(f"[DEBUG] {self.label} landed at {resp.url}")

        if resp.status_code != 200 or "/p/" not in resp.url:
            print(f"[FAIL] Entry redirect failed for {self.label}: {resp.status_code}")
            return

        # Step 2: Follow the page sequence dynamically
        current_url = resp.url
        for i in range(10):  # Limit to 10 pages
            r = self.client.get(current_url, name="/p/page")
            if r.status_code != 200:
                print(f"[FAIL] {self.label} hit error at {current_url}: {r.status_code}")
                break

            print(f"[DEBUG] {self.label} is on {current_url}")

            # If form is present, try to submit
            if "form" in r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                form = soup.find("form")
                if form:
                    post_url = form.get("action", current_url)
                    self.client.post(post_url, data={}, name="/p/submit")
                    print(f"[DEBUG] {self.label} submitted form at {post_url}")
                    current_url = post_url  # guess next step is same URL (simplified)
                else:
                    print(f"[DEBUG] No form found at {current_url}")
                    break
            else:
                print(f"[DEBUG] No form to submit at {current_url}")
                break

        print(f"[OK] {self.label} finished simulated flow ✅")
