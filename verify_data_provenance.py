"""
Verification script: proves whether data files contain live Azure data or mock data.
Checks source markers, timestamps, subscription IDs, and record content.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
MOCK = ROOT / "tests" / "mock_data"

COLLECTORS = [
    ("cost",           "costs_latest.json",          "records"),
    ("resource_graph", "resource_graph_latest.json", None),
    ("advisor",        "advisor_latest.json",        "recommendations"),
    ("aks",            "aks_metrics_latest.json",    None),
    ("metrics",        "vm_metrics_latest.json",     None),
]

SEP = "=" * 60


def check_file(label, path, records_key):
    print(f"\n{SEP}")
    print(f"  COLLECTOR: {label}")
    print(SEP)

    if not path.exists():
        print(f"  [MISSING] FILE NOT FOUND: {path}")
        return

    data = json.loads(path.read_text("utf-8"))
    meta = data.get("metadata", {})
    ingestion = data.get("ingestion", {})

    source       = meta.get("source", "NOT SET")
    generated_at = meta.get("generatedAt", "NOT SET")
    sub_id       = meta.get("subscriptionId", ingestion.get("subscriptionId", "NOT SET"))
    simulated    = ingestion.get("simulatedApi", "NOT SET")
    mock_src     = ingestion.get("mockSource") or ingestion.get("mockSources")
    ingested_at  = ingestion.get("ingestedAt", "NOT SET")

    # Determine LIVE vs MOCK
    is_live = (source == "live")
    if is_live:
        status = "[LIVE] Azure SDK"
    else:
        status = "[MOCK] local JSON"

    print(f"  STATUS          : {status}")
    print(f"  metadata.source : {source}")
    print(f"  simulatedApi    : {simulated}")
    print(f"  mockSource      : {mock_src}")
    print(f"  subscriptionId  : {sub_id}")
    print(f"  generatedAt     : {generated_at}")
    print(f"  ingestedAt      : {ingested_at}")

    # Freshness check
    if generated_at != "NOT SET":
        try:
            ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            age_mins = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            print(f"  data age        : {age_mins:.1f} minutes old")
        except Exception:
            pass

    # Record count
    if records_key:
        records = data.get(records_key, [])
        print(f"  record count    : {len(records)}")
        if records and is_live:
            print(f"  sample record   : {json.dumps(records[0], default=str)[:200]}")
    else:
        # Try common keys
        for key in ("unattachedDisks", "publicIps", "resourceInventory", "nodes", "metrics"):
            val = data.get(key)
            if val is not None:
                print(f"  {key} count  : {len(val)}")

    # Cross-check against mock file to detect identical content
    mock_file = MOCK / path.name
    if mock_file.exists():
        mock_data = json.loads(mock_file.read_text("utf-8"))
        mock_records = mock_data.get(records_key or "data", [])
        live_records = data.get(records_key or "data", [])
        if mock_records and live_records and mock_records == live_records:
            print(f"  [!!] CONTENT MATCH: data is IDENTICAL to mock file {path.name}!")
        else:
            print(f"  [OK] CONTENT DIFFERS from mock file (data is different)")
    else:
        print(f"  [--] No mock file to compare at {mock_file.name}")


print(f"\n{SEP}")
print("  AZURE DATA PROVENANCE VERIFICATION REPORT")
print(SEP)
print(f"  Env: AZURE_CLIENT_ID = {bool(os.getenv('AZURE_CLIENT_ID'))}")
print(f"  Env: AZURE_CLIENT_SECRET = {bool(os.getenv('AZURE_CLIENT_SECRET'))}")
print(f"  Env: AZURE_SUBSCRIPTION_ID = {os.getenv('AZURE_SUBSCRIPTION_ID', 'NOT SET')}")

from dotenv import load_dotenv
load_dotenv()
from src.config import get_settings
s = get_settings()
print(f"  Settings.azure_credentials_configured = {s.azure_credentials_configured}")

for label, filename, key in COLLECTORS:
    check_file(label, RAW / filename, key)

print(f"\n{SEP}")
print("  SUMMARY")
print(SEP)
live_count = 0
mock_count = 0
for label, filename, key in COLLECTORS:
    p = RAW / filename
    if p.exists():
        d = json.loads(p.read_text("utf-8"))
        src = d.get("metadata", {}).get("source", "NOT SET")
        if src == "live":
            live_count += 1
        else:
            mock_count += 1
print(f"  LIVE collectors : {live_count}")
print(f"  MOCK collectors : {mock_count}")
print(SEP)
