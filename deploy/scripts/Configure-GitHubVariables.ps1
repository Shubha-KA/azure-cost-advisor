param(
    [string]$Repository = "Shubha-KA/azure-cost-advisor",
    [Parameter(Mandatory = $true)]
    [string]$AzureClientId,
    [Parameter(Mandatory = $true)]
    [string]$AzureTenantId,
    [Parameter(Mandatory = $true)]
    [string]$AzureSubscriptionId,
    [string]$StateResourceGroup = "",
    [string]$StateStorageAccount = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is required. Install it and authenticate with gh auth login."
}

$common = @{
    AZURE_CLIENT_ID       = $AzureClientId
    AZURE_TENANT_ID       = $AzureTenantId
    AZURE_SUBSCRIPTION_ID = $AzureSubscriptionId
}

if ($StateResourceGroup) {
    $common.TF_STATE_RESOURCE_GROUP = $StateResourceGroup
}
if ($StateStorageAccount) {
    $common.TF_STATE_STORAGE_ACCOUNT = $StateStorageAccount
}

foreach ($environment in @("dev")) {
    gh api --method PUT `
        -H "Accept: application/vnd.github+json" `
        "/repos/$Repository/environments/$environment" | Out-Null

    foreach ($entry in $common.GetEnumerator()) {
        gh variable set $entry.Key `
            --repo $Repository `
            --env $environment `
            --body $entry.Value
    }
}

Write-Output "GitHub environment variables configured for dev."
