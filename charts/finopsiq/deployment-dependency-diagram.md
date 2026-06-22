# FinsOpsIQ Deployment Dependency Diagram

```text
frontend
  │
  ▼
api-gateway
  │
  ├──► auth-service
  │       │
  │       ▼
  │     collection-service
  │       │
  │       ▼
  │     Azure Service Bus
  │
  ├──► processing-service
  │       │
  │       ▼
  │     Cosmos DB
  │
  └──► ai-service
          │
          ├──► Azure AI Search
          │
          └──► Azure OpenAI
```

## Runtime notes

- `frontend` is public-facing through AGIC and calls `api-gateway`.
- `api-gateway` is the public API entrypoint and routes requests to internal services.
- `auth-service` owns Microsoft authentication, sessions, onboarding, and collection triggers.
- `collection-service` collects Azure data and publishes/forwards processing events.
- `processing-service` normalizes collected data and persists cost/resource/recommendation facts in Cosmos DB.
- `ai-service` answers FinOps questions using structured facts plus Azure AI Search and Azure OpenAI where applicable.
