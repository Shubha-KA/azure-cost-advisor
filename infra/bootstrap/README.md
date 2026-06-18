# Terraform State Bootstrap

This root module is intentionally applied with local state once. It creates the
RBAC-only Azure Blob backend used by the dev platform environment.

The storage account has public network access disabled and is exposed through
a dedicated private endpoint and private DNS zone. Peer the state VNet with the
deployment-runner VNet, or place the runner in the state VNet, before using the
backend. Azure Blob leases provide Terraform state locking.

```powershell
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap plan -var-file=environments/platform.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
terraform -chdir=infra/bootstrap output -json backend_configuration
```

Create `infra/aks/backend.dev.hcl` from the output. This file is
deployment-local and must not contain credentials.
