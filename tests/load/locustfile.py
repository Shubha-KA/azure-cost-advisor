import os
import random

from locust import HttpUser, between, task


class FinOpsUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        tenant = random.randint(0, 99)
        subscription = random.randint(0, 9)
        self.headers = {
            "X-Tenant-ID": f"tenant-{tenant}",
            "X-Subscription-ID": f"subscription-{tenant}-{subscription}",
            "Authorization": f"Bearer {os.getenv('LOAD_TEST_TOKEN', '')}",
        }

    @task(5)
    def costs(self):
        self.client.get("/api/costs/summary", headers=self.headers)

    @task(3)
    def resources(self):
        self.client.get("/api/resources", headers=self.headers)

    @task(1)
    def chat(self):
        self.client.post(
            "/api/chat",
            headers=self.headers,
            json={"message": "Summarize current cost opportunities"},
        )
