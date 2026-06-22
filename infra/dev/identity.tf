data "azurerm_client_config" "current" {}
data "azuread_client_config" "current" {}

data "azuread_service_principal" "azure_service_management" {
  client_id = "797f4846-ba00-4fd7-ba43-dac1f8f63013"
}

resource "azuread_application" "login" {
  display_name     = "azure-cost-advisor-${var.environment}-login"
  sign_in_audience = "AzureADandPersonalMicrosoftAccount"
  owners           = [data.azuread_client_config.current.object_id]

  web {
    redirect_uris = var.entra_login_redirect_uris

    implicit_grant {
      access_token_issuance_enabled = false
      id_token_issuance_enabled     = true
    }
  }

  required_resource_access {
    resource_app_id = data.azuread_service_principal.azure_service_management.client_id

    resource_access {
      id   = "41094075-9dad-400e-a0bd-54e686782033"
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "login" {
  client_id                    = azuread_application.login.client_id
  app_role_assignment_required = false
}

resource "azuread_application_password" "login" {
  application_id = azuread_application.login.id
  display_name   = "terraform-managed"
  end_date       = "2030-01-01T00:00:00Z"
}

resource "azuread_application" "collection" {
  display_name     = "azure-cost-advisor-${var.environment}-collection"
  sign_in_audience = "AzureADandPersonalMicrosoftAccount"
  owners           = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "collection" {
  client_id                    = azuread_application.collection.client_id
  app_role_assignment_required = false
}

resource "random_uuid" "internal_api_access" {}

resource "azuread_application" "internal_api" {
  display_name     = "azure-cost-advisor-${var.environment}-internal-api"
  sign_in_audience = "AzureADandPersonalMicrosoftAccount"
  owners           = [data.azuread_client_config.current.object_id]

  app_role {
    allowed_member_types = ["Application"]
    description          = "Allows the API gateway to call internal platform services."
    display_name         = "Access internal services"
    enabled              = true
    id                   = random_uuid.internal_api_access.result
    value                = "InternalService.Access"
  }
}

resource "azuread_service_principal" "internal_api" {
  client_id                    = azuread_application.internal_api.client_id
  app_role_assignment_required = true
}

resource "azuread_app_role_assignment" "gateway_internal_api" {
  app_role_id         = random_uuid.internal_api_access.result
  principal_object_id = module.identities.principal_ids["api-gateway"]
  resource_object_id  = azuread_service_principal.internal_api.object_id
}

resource "azuread_application_federated_identity_credential" "collection_aks" {
  application_id = azuread_application.collection.id
  display_name   = "aks-${var.environment}-collection-service"
  description    = "AKS workload identity for unattended cross-tenant collection."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = module.aks.oidc_issuer_url
  subject        = "system:serviceaccount:finops-collection:collection-service"
}

resource "azuread_application_federated_identity_credential" "ai_inventory_aks" {
  application_id = azuread_application.collection.id
  display_name   = "aks-${var.environment}-ai-service-inventory"
  description    = "AKS workload identity for tenant-scoped live inventory queries."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = module.aks.oidc_issuer_url
  subject        = "system:serviceaccount:finops-ai:ai-service"
}

resource "azurerm_role_assignment" "terraform_key_vault_secrets_officer" {
  scope                = module.key_vault.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "time_sleep" "key_vault_rbac" {
  create_duration = "30s"

  depends_on = [azurerm_role_assignment.terraform_key_vault_secrets_officer]
}

resource "random_password" "api_session" {
  length  = 64
  special = true
}

locals {
  key_vault_values = {
    storage-provider                      = "cosmos"
    cosmos-endpoint                       = module.cosmos.endpoint
    cosmos-database                       = module.cosmos.database_name
    azure-storage-account-url             = module.storage.account_url
    azure-storage-container               = module.storage.container_name
    use-managed-identity                  = "true"
    key-vault-url                         = module.key_vault.vault_uri
    applicationinsights-connection-string = module.monitoring.application_insights_connection_string
    auth-mode                             = "entra"
    entra-client-id                       = azuread_application.login.client_id
    entra-client-secret                   = azuread_application_password.login.value
    entra-authority                       = "https://login.microsoftonline.com/organizations"
    entra-redirect-uri                    = var.entra_login_redirect_uris[0]
    entra-post-logout-redirect-uri        = var.entra_post_logout_redirect_uri
    api-session-secret                    = random_password.api_session.result
    api-cors-origins                      = var.api_cors_origins
    frontend-url                          = var.frontend_url
    api-session-cookie-secure             = startswith(var.frontend_url, "https://") ? "true" : "false"
    service-bus-namespace                 = module.service_bus.namespace_fqdn
    service-bus-topic                     = "finops-events"
    event-provider                        = "service_bus"
    internal-api-audience                 = azuread_application.internal_api.client_id
    auth-service-url                      = "http://auth-service.finops-auth.svc.cluster.local:8000"
    collection-service-url                = "http://collection-service.finops-collection.svc.cluster.local:8000"
    processing-service-url                = "http://processing-service.finops-processing.svc.cluster.local:8000"
    ai-service-url                        = "http://ai-service.finops-ai.svc.cluster.local:8000"
    notification-service-url              = "http://notification-service.finops-notification.svc.cluster.local:8000"
    collection-entra-client-id            = azuread_application.collection.client_id
    collection-mode                       = "live"
    collection-scheduler-enabled          = "true"
    collection-interval-minutes           = tostring(var.collection_interval_minutes)
    search-provider                       = "azure_ai_search"
    azure-search-endpoint                 = module.search.endpoint
    azure-search-index-name               = "finops-knowledge"
    azure-search-semantic-config          = "finops-semantic"
    azure-search-vector-dimensions        = "1536"
    azure-openai-endpoint                 = data.azurerm_cognitive_account.openai.endpoint
    azure-openai-api-version              = "2024-08-01-preview"
    azure-openai-deployment-name          = var.openai_chat_deployment
    azure-openai-embedding-deployment     = var.openai_embedding_deployment
  }
}

resource "azurerm_key_vault_secret" "application_configuration" {
  for_each = local.key_vault_values

  name         = each.key
  value        = each.value
  key_vault_id = module.key_vault.id

  depends_on = [time_sleep.key_vault_rbac]
}
