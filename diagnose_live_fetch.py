"""
Diagnostic: traces exactly what happens when each collector tries _fetch_live_data.
Shows whether DefaultAzureCredential can authenticate and what errors occur.
"""
import sys
import os
import logging
import traceback
sys.stdout.reconfigure(encoding="utf-8")

# Load .env into os.environ BEFORE anything else
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("diagnostic")

from src.config import get_settings
settings = get_settings()

SEP = "=" * 60
print(f"\n{SEP}")
print("  DIAGNOSTIC: Live Fetch Code Path Trace")
print(SEP)

# 1. Check environment variables
print("\n[1] ENVIRONMENT VARIABLES (os.environ)")
for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
    val = os.environ.get(key, "NOT SET")
    if key == "AZURE_CLIENT_SECRET" and val != "NOT SET":
        val = val[:4] + "****"
    elif val != "NOT SET":
        val = val[:8] + "..."
    print(f"  {key} = {val}")

print(f"\n  settings.azure_credentials_configured = {settings.azure_credentials_configured}")

# 2. Test DefaultAzureCredential
print(f"\n[2] TESTING DefaultAzureCredential")
try:
    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    token = cred.get_token("https://management.azure.com/.default")
    print(f"  [OK] Token acquired successfully (expires: {token.expires_on})")
except Exception as e:
    print(f"  [FAIL] {e}")
    traceback.print_exc()

# 3. Test each collector's _fetch_live_data individually
collectors_to_test = []
try:
    from src.collector.cost_collector import CostCollector
    collectors_to_test.append(("CostCollector", CostCollector()))
except Exception as e:
    print(f"  [FAIL] Could not import CostCollector: {e}")

try:
    from src.collector.resource_graph_collector import ResourceGraphCollector
    collectors_to_test.append(("ResourceGraphCollector", ResourceGraphCollector()))
except Exception as e:
    print(f"  [FAIL] Could not import ResourceGraphCollector: {e}")

try:
    from src.collector.advisor_collector import AdvisorCollector
    collectors_to_test.append(("AdvisorCollector", AdvisorCollector()))
except Exception as e:
    print(f"  [FAIL] Could not import AdvisorCollector: {e}")

for name, collector in collectors_to_test:
    print(f"\n{SEP}")
    print(f"  [3] TESTING: {name}._fetch_live_data()")
    print(SEP)
    try:
        payload = collector._fetch_live_data()
        meta = payload.get("metadata", {})
        print(f"  [OK] Live fetch succeeded!")
        print(f"    metadata.source      = {meta.get('source', 'NOT SET')}")
        print(f"    metadata.subscriptionId = {meta.get('subscriptionId', 'NOT SET')}")
        print(f"    metadata.generatedAt = {meta.get('generatedAt', 'NOT SET')}")
        
        # Count records
        for key in ("records", "recommendations", "unattachedDisks", "publicIps", "resourceInventory"):
            if key in payload:
                print(f"    {key} count = {len(payload[key])}")
    except NotImplementedError as e:
        print(f"  [SKIP] Not implemented: {e}")
    except Exception as e:
        print(f"  [FAIL] Live fetch FAILED with exception:")
        print(f"    {type(e).__name__}: {e}")
        traceback.print_exc()

# 4. Now run collect() on CostCollector and check the output
print(f"\n{SEP}")
print("  [4] RUNNING CostCollector.collect() - Full Pipeline")
print(SEP)
try:
    cc = CostCollector()
    result = cc.collect()
    print(f"  collector    = {result.collector}")
    print(f"  source_file  = {result.source_file}")
    print(f"  record_count = {result.record_count}")
    print(f"  output_path  = {result.output_path}")
    
    # Read the output and check
    import json
    from pathlib import Path
    data = json.loads(Path(result.latest_path).read_text("utf-8"))
    ingestion = data.get("ingestion", {})
    meta = data.get("metadata", {})
    print(f"  OUTPUT CHECK:")
    print(f"    metadata.source   = {meta.get('source', 'NOT SET')}")
    print(f"    simulatedApi      = {ingestion.get('simulatedApi', 'NOT SET')}")
    print(f"    mockSource        = {ingestion.get('mockSource', 'NOT SET')}")
    print(f"    subscriptionId    = {meta.get('subscriptionId', ingestion.get('subscriptionId', 'NOT SET'))}")
except Exception as e:
    print(f"  [FAIL] {e}")
    traceback.print_exc()

print(f"\n{SEP}")
print("  DIAGNOSTIC COMPLETE")
print(SEP)
