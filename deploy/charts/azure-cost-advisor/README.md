# AKS Helm Deployment

The chart creates:

- six workload namespaces plus the edge namespace
- seven workload-identity ServiceAccounts
- seven Key Vault `SecretProviderClass` resources
- seven Deployments and ClusterIP Services
- single-replica Deployments without HPAs
- Application Gateway Ingress resources for the frontend and API Gateway

It intentionally creates no Kubernetes `Secret` or `ConfigMap`. Key Vault
objects are mounted by the Secrets Store CSI driver. The startup shell exports
the mounted files into the application process environment.

Populate every object named in `deploy/keyvault/required-objects.txt` before
installing the chart. Values files contain image and Azure resource references
only.

The deployment script renders with Helm and applies with `kubectl`. It does not
use `helm install`, because Helm's default release storage would create a
Kubernetes Secret.

```powershell
.\deploy\scripts\Deploy-Aks.ps1 -Environment dev -ImageTag <immutable-tag>
```
