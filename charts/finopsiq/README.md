# FinsOpsIQ AKS Helm Chart

This chart deploys the existing FinsOpsIQ microservices to one AKS namespace per environment.

Feature/business logic changes are intentionally out of scope for this chart.

## Structure

```text
charts/finopsiq/
  Chart.yaml
  values.yaml
  values-dev.yaml
  values-prod.yaml
  deployment-dependency-diagram.md
  templates/
    namespace/
      namespace.yaml
    frontend/
      deployment.yaml
      service.yaml
      hpa.yaml
    api-gateway/
      deployment.yaml
      service.yaml
      hpa.yaml
    auth-service/
      serviceaccount.yaml
      deployment.yaml
      service.yaml
      hpa.yaml
    collection-service/
      serviceaccount.yaml
      deployment.yaml
      service.yaml
      hpa.yaml
    processing-service/
      serviceaccount.yaml
      deployment.yaml
      service.yaml
      hpa.yaml
    ai-service/
      serviceaccount.yaml
      deployment.yaml
      service.yaml
      hpa.yaml
    notification-service/
      serviceaccount.yaml
      deployment.yaml
      service.yaml
      hpa.yaml
    ingress/
      ingress.yaml
```

No `_helpers.tpl` is used.

## Required secret

Each environment must provide one Kubernetes secret before deployment:

```text
finopsiq-dev-app-config
finopsiq-prod-app-config
```

The secret must be generated from Azure Key Vault integration or another approved Key Vault-backed secret sync process. Do not commit secret values.

The application expects the same environment variable contract proven in Docker Compose, including storage, Entra, Cosmos, Service Bus, OpenAI, AI Search, Storage, and session settings.

## Workload Identity

Only Azure-integrated workloads have Kubernetes ServiceAccounts with:

```text
azure.workload.identity/client-id
```

Those workloads are:

- auth-service
- collection-service
- processing-service
- ai-service
- notification-service

Frontend and api-gateway intentionally use the default service account and do not receive Workload Identity annotations.

Every Workload Identity pod template has:

```text
azure.workload.identity/use: "true"
USE_MANAGED_IDENTITY=true
```

Federated Identity Credentials must be created for each service account outside this chart.

## Render validation

Example:

```powershell
docker run --rm -v ${PWD}:/work -w /work alpine/helm:3.15.4 template finopsiq charts/finopsiq -f charts/finopsiq/values-dev.yaml `
  --set services.frontend.image.repository=<acr>/frontend `
  --set services.apiGateway.image.repository=<acr>/api-gateway `
  --set services.auth.image.repository=<acr>/auth-service `
  --set services.collection.image.repository=<acr>/collection-service `
  --set services.processing.image.repository=<acr>/processing-service `
  --set services.ai.image.repository=<acr>/ai-service `
  --set services.notification.image.repository=<acr>/notification-service `
  --set services.auth.serviceAccountClientId=<auth-managed-identity-client-id> `
  --set services.collection.serviceAccountClientId=<collection-managed-identity-client-id> `
  --set services.processing.serviceAccountClientId=<processing-managed-identity-client-id> `
  --set services.ai.serviceAccountClientId=<ai-managed-identity-client-id> `
  --set services.notification.serviceAccountClientId=<notification-managed-identity-client-id>
```

## Deployment

```powershell
helm upgrade --install finopsiq-dev charts/finopsiq `
  --namespace finopsiq-dev `
  --create-namespace `
  -f charts/finopsiq/values-dev.yaml `
  --set services.frontend.image.repository=<acr>/frontend `
  --set services.apiGateway.image.repository=<acr>/api-gateway `
  --set services.auth.image.repository=<acr>/auth-service `
  --set services.collection.image.repository=<acr>/collection-service `
  --set services.processing.image.repository=<acr>/processing-service `
  --set services.ai.image.repository=<acr>/ai-service `
  --set services.notification.image.repository=<acr>/notification-service `
  --set services.auth.serviceAccountClientId=<auth-managed-identity-client-id> `
  --set services.collection.serviceAccountClientId=<collection-managed-identity-client-id> `
  --set services.processing.serviceAccountClientId=<processing-managed-identity-client-id> `
  --set services.ai.serviceAccountClientId=<ai-managed-identity-client-id> `
  --set services.notification.serviceAccountClientId=<notification-managed-identity-client-id>
```

Use `values-prod.yaml` and namespace `finopsiq-prod` for production.

## Required validation after deployment

- Pods ready: all services have 2 ready replicas.
- Probes: all Python services respond on `/health/live` and `/health/ready`; frontend responds on `/`.
- Ingress: AGIC routes `/` to frontend and `/api` to api-gateway.
- Key Vault: Kubernetes secret exists and no secret values are logged.
- Cosmos DB: reads and writes work.
- Service Bus: event publishing and consumption work.
- Azure OpenAI: chat and embeddings work.
- Azure AI Search: index is reachable and RAG queries execute.
- Storage Account: read/write paths work.
- Azure APIs: Resource Graph, Cost Management, Advisor, and Monitor collection work.
- App flows: login, logout, onboarding, collection, processing, dashboard, recommendations, and AI assistant.
