param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("dev")]
    [string]$Environment,

    [Parameter(Mandatory = $true)]
    [string]$ImageTag,

    [switch]$SkipCredentials
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$terraformRoot = Join-Path $root "infra\dev"
$chart = Join-Path $root "deploy\charts\azure-cost-advisor"
$values = Join-Path $chart "values-$Environment.yaml"

if (-not (Test-Path (Join-Path $terraformRoot "main.tf"))) {
    throw "Terraform root not found: $terraformRoot"
}
if (-not (Test-Path (Join-Path $chart "Chart.yaml"))) {
    throw "Helm chart not found: $chart"
}
if (-not (Test-Path $values)) {
    throw "Helm values file not found: $values"
}

$outputs = terraform -chdir=$terraformRoot output -json | ConvertFrom-Json
$resourceGroup = $outputs.resource_group_name.value
$clusterName = $outputs.aks_cluster_name.value
$vaultName = $outputs.key_vault_name.value
$tenantId = $outputs.platform_tenant_id.value
$acr = $outputs.acr_login_server.value
$clientIds = $outputs.workload_identity_client_ids.value

if (-not $SkipCredentials) {
    az aks get-credentials `
        --resource-group $resourceGroup `
        --name $clusterName `
        --overwrite-existing
}

& (Join-Path $PSScriptRoot "Test-KeyVaultObjects.ps1") -VaultName $vaultName

$arguments = @(
    "template", "finops", $chart,
    "--values", $values,
    "--set", "global.keyVault.name=$vaultName",
    "--set", "global.keyVault.tenantId=$tenantId"
)

foreach ($service in $clientIds.PSObject.Properties.Name) {
    $arguments += @(
        "--set", "services.$service.workloadIdentityClientId=$($clientIds.$service)",
        "--set", "services.$service.image.repository=$acr/$service",
        "--set", "services.$service.image.tag=$ImageTag"
    )
}

helm @arguments | kubectl apply -f -
