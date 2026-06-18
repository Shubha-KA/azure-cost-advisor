import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.costmanagement.models import QueryDefinition, QueryDataset, QueryAggregation, QueryGrouping, QueryTimePeriod
from datetime import datetime, timezone, timedelta

# Load credentials
load_dotenv()
sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
cred = DefaultAzureCredential()

print("\n--- DIRECT AZURE SDK VERIFICATION ---")
print(f"Subscription ID: {sub_id}")

# 1. Resource Groups currently existing in Azure
print("\n1. RESOURCE GROUPS CURRENTLY EXISTING IN AZURE (Resource Management API):")
try:
    rm_client = ResourceManagementClient(cred, sub_id)
    rgs = list(rm_client.resource_groups.list())
    print(f"Total current Resource Groups: {len(rgs)}")
    for rg in rgs:
        print(f"  - {rg.name}")
except Exception as e:
    print(f"Error: {e}")

# 2. Resource Groups returned by Cost Management
print("\n2. RESOURCE GROUPS RETURNED BY COST MANAGEMENT API (Last 30 Days):")
try:
    cost_client = CostManagementClient(cred)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    query = QueryDefinition(
        type="Usage",
        timeframe="Custom",
        time_period=QueryTimePeriod(from_property=start, to=now),
        dataset=QueryDataset(
            granularity="Daily",
            aggregation={"totalCost": QueryAggregation(name="PreTaxCost", function="Sum")},
            grouping=[QueryGrouping(type="Dimension", name="ResourceGroup")]
        )
    )
    res = cost_client.query.usage(scope=f"/subscriptions/{sub_id}", parameters=query)
    
    cost_rgs = set()
    for row in res.rows:
        rg = row[1]
        if rg: cost_rgs.add(rg)
        
    print(f"Total Resource Groups with Cost in last 30 days: {len(cost_rgs)}")
    for rg in sorted(cost_rgs):
        print(f"  - {rg}")
        
    print("\nExplanation: Cost Management returns historical usage. Even if you deleted a resource group, if it incurred cost in the last 30 days, Azure includes it in the cost payload.")
except Exception as e:
    print(f"Error: {e}")
