# Terraform Infrastructure Pipeline - DEV

Workflow:

```text
.github/workflows/terraform-infra.yml
```

Scope:

- DEV only
- `main` branch only
- Terraform root: `terraform/environments/dev`
- Infrastructure only
- No AKS or Helm deployment
- No application deployment

## Trigger Rules

The workflow runs on:

- pull requests targeting `main`
- pushes to `main`
- daily schedule at `06:00 UTC`

Only changes under this path trigger the workflow:

```text
terraform/**
```

## Required GitHub Secrets

Configure these as repository or environment secrets:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
SLACK_WEBHOOK_URL
```

No `AZURE_CLIENT_SECRET` is used.

## Required GitHub Variables

Configure these as repository or environment variables:

```text
TF_STATE_RESOURCE_GROUP
TF_STATE_STORAGE_ACCOUNT
TF_STATE_CONTAINER
```

The workflow uses a fixed DEV state key:

```text
dev/terraform.tfstate
```

## Required GitHub Environment Configuration

Create a GitHub Environment named:

```text
dev
```

Required protection:

- Enable required reviewers.
- Restrict deployment branches to `main`.

The `terraform_apply` job uses:

```yaml
environment: dev
```

This provides native GitHub manual approval before apply.

## Required Azure Federated Credential Configuration

Create a federated identity credential on the Azure application or user-assigned managed identity represented by `AZURE_CLIENT_ID`.

Issuer:

```text
https://token.actions.githubusercontent.com
```

Audience:

```text
api://AzureADTokenExchange
```

Subject for main branch:

```text
repo:<OWNER>/<REPO>:ref:refs/heads/main
```

If pull requests also need Azure login during plan validation, add:

```text
repo:<OWNER>/<REPO>:pull_request
```

The principal must have permissions to read/write the Terraform backend and manage DEV infrastructure.

## Remote Backend Verification

Backend configuration is declared in:

```text
terraform/environments/dev/backend.tf
```

```hcl
terraform {
  backend "azurerm" {}
}
```

The workflow initializes the backend with:

```bash
terraform init \
  -backend-config="resource_group_name=${TF_STATE_RESOURCE_GROUP}" \
  -backend-config="storage_account_name=${TF_STATE_STORAGE_ACCOUNT}" \
  -backend-config="container_name=${TF_STATE_CONTAINER}" \
  -backend-config="key=dev/terraform.tfstate" \
  -backend-config="use_azuread_auth=true"
```

State file strategy:

```text
DEV:  dev/terraform.tfstate
PROD: prod/terraform.tfstate
```

State locking:

- The AzureRM backend stores state in Azure Blob Storage.
- Terraform uses Azure Blob leases for state locking.
- A concurrent run attempting to modify the same state key will fail to acquire the blob lease until the lock is released.
- GitHub Actions also prevents concurrent DEV deployments with:

```yaml
concurrency:
  group: terraform-dev
  cancel-in-progress: false
```

## Slack Message Templates

### Plan Ready

```text
Environment: DEV
Status: PLAN READY
Repository: <repo>
Commit: <sha>
Author: <actor>
Terraform Plan Summary: Add: <n>, Modify: <n>, Destroy: <n>
Cost Estimate: Infracost placeholder only

Terraform plan completed. Awaiting approval.
```

### Success

```text
Environment: DEV
Status: SUCCESS
Resources created: <n>
Resources updated: <n>
Deployment duration: <seconds>s
```

### Failure

```text
Environment: DEV
Status: FAILED
Failed stage: <stage>
Workflow URL: <url>
Commit SHA: <sha>
```

### Drift Detected

```text
Environment: DEV
Status: DRIFT DETECTED
Plan Summary: Add: <n>, Modify: <n>, Destroy: <n>
Workflow URL: <url>

No automatic correction was applied.
```

## Drift Detection

Scheduled drift detection runs:

```bash
terraform plan -detailed-exitcode
```

Behavior:

| Exit Code | Meaning | Pipeline Behavior |
|---:|---|---|
| 0 | No drift | Publish no-drift summary |
| 2 | Drift detected | Send Slack alert; do not apply |
| 1 | Failure | Send Slack failure alert |

## Pipeline Execution Flow

```text
terraform/** change
  │
  ▼
Stage 1: Security Scan
  └─ tfsec, fail HIGH/CRITICAL
  │
  ▼
Stage 2: Terraform Quality
  ├─ terraform fmt -check -recursive
  ├─ terraform init
  └─ terraform validate
  │
  ▼
Stage 3: Terraform Plan
  ├─ terraform plan -out=dev.tfplan
  ├─ generate add/modify/destroy summary
  ├─ cost estimation placeholder
  └─ upload saved plan artifact
  │
  ▼
Stage 4: Slack Plan Ready
  │
  ▼
Stage 5: GitHub Environment Approval: dev
  │
  ▼
Stage 6: Terraform Apply
  ├─ download saved dev.tfplan artifact
  └─ terraform apply -auto-approve dev.tfplan
  │
  ▼
Stage 7: Post Deployment Validation
  ├─ terraform output
  └─ terraform state list
  │
  ▼
Stage 8: Slack Success / Failure
```

Scheduled drift flow:

```text
cron 0 6 * * *
  │
  ▼
terraform init with AzureRM backend
  │
  ▼
terraform plan -detailed-exitcode
  ├─ exit 0: no drift
  ├─ exit 2: Slack drift alert, no apply
  └─ exit 1: Slack failure alert
```

## Notes

- Pull requests run scan, quality, and plan only.
- Apply only runs for push events on `main`.
- Scheduled drift detection never applies changes.
- The saved plan artifact is retained for one day.
- Output summaries do not print sensitive output values.
- This workflow does not build Docker images, push containers, run Helm, or deploy Kubernetes workloads.
