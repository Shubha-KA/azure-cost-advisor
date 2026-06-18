import subprocess
import os
import json

directories = [
    "infra/dev",
    "infra/dev/modules/aks",
    "infra/dev/modules/application-gateway",
    "infra/dev/modules/cosmos-nosql",
    "infra/dev/modules/key-vault",
    "infra/dev/modules/network",
    "infra/dev/modules/service-bus",
    "infra/dev/modules/storage",
    "infra/dev/modules/ai-search",
    "infra/dev/modules/identities",
    "infra/dev/modules/private-endpoints",
    "infra/dev/modules/rbac",
    "infra/dev/modules/registry"
]

failed_checks = set()

for d in directories:
    if not os.path.exists(d): continue
    try:
        print(f"Scanning {d}...")
        result = subprocess.run([r".venv\Scripts\checkov.cmd", "-d", os.path.abspath(d), "-o", "json"], capture_output=True, text=True)
        if result.stdout:
            try:
                # checkov may return a list or a dict
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                for report in data:
                    results = report.get("results", {})
                    failed = results.get("failed_checks", [])
                    for check in failed:
                        failed_checks.add(check["check_id"])
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"Error on {d}: {e}")

print("FAILED_CHECKS_LIST:")
for check in sorted(list(failed_checks)):
    print(check)
