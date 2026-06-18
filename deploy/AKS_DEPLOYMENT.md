# AKS Deployment Sequence

## 1. Bootstrap State

Run from an authenticated operator workstation. Bootstrap uses local state for
its one-time apply.

```powershell
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap plan -var-file=environments/platform.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
terraform -chdir=infra/bootstrap output -json backend_configuration
```

The bootstrap creates the state resource group, RBAC-only ZRS storage account,
private container, recovery controls, deletion locks, private endpoint, private
DNS, and a dedicated state VNet.

## 2. Connect The Runner

Use a self-hosted deployment runner with network reachability to the state
private endpoint. Peer its VNet to the state VNet and link or forward the
`privatelink.blob.core.windows.net` private DNS zone.

## 3. Initialize The Platform Backend

Create `infra/aks/backend.dev.hcl` from bootstrap outputs:

```hcl
resource_group_name  = "<bootstrap output>"
storage_account_name = "<bootstrap output>"
container_name       = "tfstate"
key                  = "dev/aks-platform.tfstate"
use_azuread_auth     = true
```

Then initialize and plan:

```powershell
terraform -chdir=infra/aks init -reconfigure -backend-config=backend.dev.hcl
terraform -chdir=infra/aks plan -var-file=environments/dev.tfvars -out=dev.tfplan
terraform -chdir=infra/aks apply dev.tfplan
```

## 4. Populate Key Vault

Populate every object named in `deploy/keyvault/required-objects.txt` through a
secure operator session. Do not place values in Terraform variables, Helm
values, Kubernetes resources, or GitHub settings.

Validate names without retrieving values:

```powershell
.\deploy\scripts\Test-KeyVaultObjects.ps1 -VaultName <terraform-output>
```

The collection Entra application must also contain a federated identity
credential for the AKS issuer and
`system:serviceaccount:finops-collection:collection-service`.

## 5. Build And Push Images

Build immutable images for the frontend and six Python services, scan them, and
push them to the Terraform-created ACR.

## 6. Deploy Workloads

```powershell
.\deploy\scripts\Deploy-Aks.ps1 -Environment dev -ImageTag <immutable-tag>
```

The script renders the Helm chart and applies it with `kubectl`; no Helm release
Secret, Kubernetes Secret, or ConfigMap is created.

## 7. Verify

```powershell
kubectl get serviceaccounts --all-namespaces
kubectl get secretproviderclass --all-namespaces
kubectl get deployments,services,hpa --all-namespaces
kubectl get ingress -n finops-edge
kubectl get pods --all-namespaces -l app.kubernetes.io/part-of=azure-cost-advisor
kubectl logs -n finops-collection deploy/collection-service
```

Restart workloads after rotating Key Vault values because environment
variables are exported from CSI-mounted files only at process startup.
