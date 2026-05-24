# Infrastructure — Hub-and-Spoke with Application Gateway

## Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────┐
│  Hub VNet (10.0.0.0/16)             │
│  ┌───────────────────────────────┐  │
│  │ Application Gateway + WAF     │  │
│  │ Public IP → :80               │  │
│  └───────────────┬───────────────┘  │
└──────────────────┼──────────────────┘
                   │ VNet Peering
                   ▼
┌─────────────────────────────────────┐
│  Spoke VNet (10.1.0.0/16)           │
│  ┌───────────────────────────────┐  │
│  │ Container Apps Environment    │  │
│  │ Streamlit Dashboard :8501     │  │
│  │ (internal ingress only)       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Resources Created

| Resource | Purpose |
|----------|---------|
| Resource Group | All resources |
| Hub VNet + AppGW subnet | Application Gateway |
| Spoke VNet + CAE subnet (/23) | Container Apps |
| NSGs | Hub + spoke security rules |
| VNet Peering | Hub ↔ spoke bidirectional |
| Public IP | Internet entry |
| Application Gateway | Routing, health probe, WAF |
| Log Analytics | Container Apps diagnostics |
| Container App Environment | VNet-integrated runtime |
| Container App | Streamlit on port 8501 |

## Deploy

```bash
# Build and push image to ACR
az acr login --name myregistry
docker build -t myregistry.azurecr.io/azure-cost-advisor:latest .
docker push myregistry.azurecr.io/azure-cost-advisor:latest

cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set docker_image

export TF_VAR_azure_openai_api_key="your-key"
export TF_VAR_azure_openai_endpoint="https://your-resource.openai.azure.com/"

terraform init
terraform plan
terraform apply
```

## Outputs

```bash
terraform output dashboard_url          # http://<appgw-public-ip>
terraform output container_app_fqdn     # internal backend FQDN
```

## Container Runtime Switch

Set `container_runtime = "webapp"` in `terraform.tfvars` to use Azure Web App for Containers instead of Container Apps.

## Health Probe

Application Gateway probes `GET /_stcore/health` on port **8501** (Streamlit health endpoint).
