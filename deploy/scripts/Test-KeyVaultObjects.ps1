param(
    [Parameter(Mandatory = $true)]
    [string]$VaultName
)

$ErrorActionPreference = "Stop"
$requiredPath = Join-Path $PSScriptRoot "..\keyvault\required-objects.txt"
$required = Get-Content -LiteralPath $requiredPath |
    Where-Object { $_ -and -not $_.StartsWith("#") }
$available = az keyvault secret list `
    --vault-name $VaultName `
    --query "[].name" `
    --output tsv

$missing = @($required | Where-Object { $_ -notin $available })
if ($missing.Count -gt 0) {
    Write-Error "Key Vault is missing required objects: $($missing -join ', ')"
}

Write-Output "Key Vault object validation passed: $($required.Count) objects found."
