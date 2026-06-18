import os
import sys
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import QueryDefinition, QueryTimePeriod, QueryDataset, QueryAggregation

# Load environment variables
load_dotenv()

subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")

if not subscription_id:
    print("❌ AZURE_SUBSCRIPTION_ID is missing from your .env file!")
    sys.exit(1)

print(f"Testing authentication for Subscription: {subscription_id}")
print("-" * 50)

try:
    print("1. Authenticating with DefaultAzureCredential...")
    credential = DefaultAzureCredential()
    print("✅ Credentials initialized successfully.")
    print("-" * 50)

    # Test Resource Reader permissions
    print("2. Testing Resource Manager (Reader) permissions...")
    resource_client = ResourceManagementClient(credential, subscription_id)
    rgs = list(resource_client.resource_groups.list())
    print(f"✅ Success! Found {len(rgs)} Resource Groups.")
    for rg in rgs[:3]:
        print(f"   - {rg.name}")
    if len(rgs) > 3:
        print("   - ...")
    print("-" * 50)

    # Test Cost Management Reader permissions
    print("3. Testing Cost Management (Cost Management Reader) permissions...")
    cost_client = CostManagementClient(credential)
    scope = f"/subscriptions/{subscription_id}"
    
    # Run a tiny cost query for the last 1 day
    query = QueryDefinition(
        type="Usage",
        timeframe="TheLastMonth",
        dataset=QueryDataset(
            granularity="Daily",
            aggregation={
                "totalCost": QueryAggregation(name="PreTaxCost", function="Sum")
            }
        )
    )
    
    result = cost_client.query.usage(scope=scope, parameters=query)
    print("✅ Success! Cost Management query executed successfully.")
    row_count = len(result.rows) if result.rows else 0
    print(f"   - Query returned {row_count} rows of cost data.")
    print("-" * 50)

    print("🎉 ALL TESTS PASSED! Your Service Principal is configured correctly.")

except Exception as e:
    print("\n❌ FAILED!")
    print(f"Error Details:\n{str(e)}")
    print("\nPlease verify:")
    print("1. Your .env file contains correct AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID")
    print("2. The Service Principal has 'Reader' and 'Cost Management Reader' role assignments on the subscription.")
