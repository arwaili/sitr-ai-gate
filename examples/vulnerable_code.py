"""Synthetic vulnerable code for the Sitr demo. Every credential below is fake."""

import json
import urllib.request

API_KEY = "sk-synthetic-demo-000000000000000000"
DATABASE_URL = "postgresql://app:synthetic-pass@db.example.internal:5432/hr"


def fetch_report(report_id: str) -> dict:
    request = urllib.request.Request(
        f"https://api.example.com/reports/{report_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)
