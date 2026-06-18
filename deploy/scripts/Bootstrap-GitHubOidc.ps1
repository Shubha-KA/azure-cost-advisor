param(
    [string]$Repository = "Shubha-KA/azure-cost-advisor",
    [string]$ApplicationName = "azure-cost-advisor-github-deploy",
    [string]$SubscriptionId = "e54a7ca3-4b6b-4b0f-889d-2508c85f4f30"
)

$ErrorActionPreference = "Stop"
$microsoftGraphAppId = "00000003-0000-0000-c000-000000000000"
$applicationReadWriteOwnedByRoleId = "18a4783c-866b-4cc7-a460-3d5e5662c884"

az account set --subscription $SubscriptionId
$tenantId = az account show --query tenantId --output tsv

$application = az ad app list `
    --filter "displayName eq '$ApplicationName'" `
    --query "[0]" `
    --output json | ConvertFrom-Json

if (-not $application) {
    $requiredAccess = @(
        @{
            resourceAppId  = $microsoftGraphAppId
            resourceAccess = @(
                @{
                    id   = $applicationReadWriteOwnedByRoleId
                    type = "Role"
                }
            )
        }
    )
    $requiredAccessPath = Join-Path $env:TEMP "azure-cost-advisor-required-resource-access.json"
    $requiredAccess | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $requiredAccessPath
    try {
        $application = az ad app create `
            --display-name $ApplicationName `
            --sign-in-audience AzureADMyOrg `
            --required-resource-accesses "@$requiredAccessPath" `
            --query "{id:id,appId:appId,displayName:displayName}" `
            --output json | ConvertFrom-Json
    }
    finally {
        Remove-Item -LiteralPath $requiredAccessPath -Force -ErrorAction SilentlyContinue
    }
}

$servicePrincipal = az ad sp list `
    --filter "appId eq '$($application.appId)'" `
    --query "[0].{id:id,appId:appId}" `
    --output json | ConvertFrom-Json

if (-not $servicePrincipal) {
    $servicePrincipal = az ad sp create `
        --id $application.appId `
        --query "{id:id,appId:appId}" `
        --output json | ConvertFrom-Json
}

$subjects = [ordered]@{
    "github-main" = "repo:${Repository}:ref:refs/heads/main"
    "github-dev"  = "repo:${Repository}:environment:dev"
}

$existingCredentials = az ad app federated-credential list `
    --id $application.id `
    --query "[].name" `
    --output tsv

foreach ($entry in $subjects.GetEnumerator()) {
    if ($entry.Key -in $existingCredentials) {
        continue
    }

    $credential = @{
        name        = $entry.Key
        issuer      = "https://token.actions.githubusercontent.com"
        subject     = $entry.Value
        audiences   = @("api://AzureADTokenExchange")
        description = "GitHub Actions OIDC trust for $($entry.Value)"
    }
    $credentialPath = Join-Path $env:TEMP "$($entry.Key)-federated-credential.json"
    $credential | ConvertTo-Json | Set-Content -LiteralPath $credentialPath
    try {
        az ad app federated-credential create `
            --id $application.id `
            --parameters $credentialPath `
            --only-show-errors | Out-Null
    }
    finally {
        Remove-Item -LiteralPath $credentialPath -Force -ErrorAction SilentlyContinue
    }
}

$subscriptionScope = "/subscriptions/$SubscriptionId"
foreach ($role in @("Contributor", "Role Based Access Control Administrator")) {
    $assignment = az role assignment list `
        --assignee-object-id $servicePrincipal.id `
        --scope $subscriptionScope `
        --role $role `
        --query "[0].id" `
        --output tsv
    if (-not $assignment) {
        az role assignment create `
            --assignee-object-id $servicePrincipal.id `
            --assignee-principal-type ServicePrincipal `
            --scope $subscriptionScope `
            --role $role `
            --only-show-errors | Out-Null
    }
}

$graphServicePrincipalId = az ad sp show `
    --id $microsoftGraphAppId `
    --query id `
    --output tsv
$graphAssignment = az rest `
    --method GET `
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($servicePrincipal.id)/appRoleAssignments" `
    --query "value[?appRoleId == '$applicationReadWriteOwnedByRoleId'].id | [0]" `
    --output tsv

if (-not $graphAssignment) {
    $assignment = @{
        principalId = $servicePrincipal.id
        resourceId  = $graphServicePrincipalId
        appRoleId   = $applicationReadWriteOwnedByRoleId
    }
    $assignmentPath = Join-Path $env:TEMP "github-graph-app-role.json"
    $assignment | ConvertTo-Json | Set-Content -LiteralPath $assignmentPath
    try {
        az rest `
            --method POST `
            --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($servicePrincipal.id)/appRoleAssignments" `
            --headers "Content-Type=application/json" `
            --body "@$assignmentPath" `
            --only-show-errors | Out-Null
    }
    finally {
        Remove-Item -LiteralPath $assignmentPath -Force -ErrorAction SilentlyContinue
    }
}

[pscustomobject]@{
    AZURE_CLIENT_ID       = $application.appId
    AZURE_TENANT_ID       = $tenantId
    AZURE_SUBSCRIPTION_ID = $SubscriptionId
    SERVICE_PRINCIPAL_ID  = $servicePrincipal.id
} | ConvertTo-Json
