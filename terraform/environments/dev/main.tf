terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  features {}
}

locals {
  common_tags = merge(
    {
      Environment = var.environment
      Owner       = var.owner
    },
    var.extra_tags
  )

  workload_identity_subjects = {
    for key, service_account in var.workload_service_accounts :
    key => "system:serviceaccount:${var.helm_namespace}:${service_account}"
  }
}

module "resource_group" {
  source   = "../../modules/resource-group"
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

module "network" {
  source              = "../../modules/network"
  name                = var.network.name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  address_space       = var.network.address_space
  subnets             = var.network.subnets
  tags                = local.common_tags
}

module "monitor" {
  source              = "../../modules/monitor"
  name                = var.monitor.name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  sku                 = var.monitor.sku
  retention_in_days   = var.monitor.retention_in_days
  tags                = local.common_tags
}

module "application_insights" {
  source              = "../../modules/application-insights"
  name                = var.application_insights.name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  workspace_id        = module.monitor.id
  application_type    = var.application_insights.application_type
  tags                = local.common_tags
}

module "acr" {
  source              = "../../modules/acr"
  name                = var.acr.name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  sku                 = var.acr.sku
  tags                = local.common_tags
}

module "keyvault" {
  source                        = "../../modules/keyvault"
  name                          = var.keyvault.name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  tenant_id                     = var.tenant_id
  sku_name                      = var.keyvault.sku_name
  enable_rbac_authorization     = var.keyvault.enable_rbac_authorization
  purge_protection_enabled      = var.keyvault.purge_protection_enabled
  soft_delete_retention_days    = var.keyvault.soft_delete_retention_days
  public_network_access_enabled = var.keyvault.public_network_access_enabled
  tags                          = local.common_tags
}

module "cosmosdb" {
  source                        = "../../modules/cosmosdb"
  account_name                  = var.cosmosdb.account_name
  database_name                 = var.cosmosdb.database_name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  consistency_level             = var.cosmosdb.consistency_level
  database_throughput           = var.cosmosdb.database_throughput
  containers                    = var.cosmosdb.containers
  public_network_access_enabled = var.cosmosdb.public_network_access_enabled
  local_authentication_disabled = var.cosmosdb.local_authentication_disabled
  free_tier_enabled             = var.cosmosdb.free_tier_enabled
  tags                          = local.common_tags
}

module "servicebus" {
  source              = "../../modules/servicebus"
  namespace_name      = var.servicebus.namespace_name
  topic_name          = var.servicebus.topic_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  sku                 = var.servicebus.sku
  capacity            = var.servicebus.capacity
  tags                = local.common_tags
}

module "storage" {
  source                        = "../../modules/storage"
  account_name                  = var.storage.account_name
  container_name                = var.storage.container_name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  account_tier                  = var.storage.account_tier
  account_replication_type      = var.storage.account_replication_type
  public_network_access_enabled = var.storage.public_network_access_enabled
  tags                          = local.common_tags
}

module "ai_search" {
  source                        = "../../modules/ai-search"
  name                          = var.ai_search.name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  sku                           = var.ai_search.sku
  replica_count                 = var.ai_search.replica_count
  partition_count               = var.ai_search.partition_count
  public_network_access_enabled = var.ai_search.public_network_access_enabled
  local_authentication_enabled  = var.ai_search.local_authentication_enabled
  tags                          = local.common_tags
}

module "openai" {
  source                        = "../../modules/openai"
  name                          = var.openai.name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  sku_name                      = var.openai.sku_name
  custom_subdomain_name         = var.openai.custom_subdomain_name
  public_network_access_enabled = var.openai.public_network_access_enabled
  local_auth_enabled            = var.openai.local_auth_enabled
  deployments                   = var.openai.deployments
  tags                          = local.common_tags
}

module "managed_identity" {
  source              = "../../modules/managed-identity"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  identities          = var.managed_identities
  tags                = local.common_tags
}

module "aks" {
  source              = "../../modules/aks"
  name                = var.aks.name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  dns_prefix          = var.aks.dns_prefix
  kubernetes_version  = var.aks.kubernetes_version
  tenant_id           = var.tenant_id
  aks_subnet_id       = module.network.subnet_ids[var.aks.subnet_key]
  cluster_identity_id = module.managed_identity.identity_ids[var.aks.cluster_identity_key]
  kubelet_identity = {
    identity_id = module.managed_identity.identity_ids[var.aks.kubelet_identity_key]
    client_id   = module.managed_identity.client_ids[var.aks.kubelet_identity_key]
    object_id   = module.managed_identity.principal_ids[var.aks.kubelet_identity_key]
  }
  system_node_pool           = var.aks.system_node_pool
  user_node_pools            = var.aks.user_node_pools
  network_policy             = var.aks.network_policy
  service_cidr               = var.aks.service_cidr
  dns_service_ip             = var.aks.dns_service_ip
  azure_rbac_enabled         = var.aks.azure_rbac_enabled
  log_analytics_workspace_id = module.monitor.id
  tags                       = local.common_tags
}

module "workload_identity" {
  source              = "../../modules/workload-identity"
  resource_group_name = module.resource_group.name
  federated_credentials = {
    for key, subject in local.workload_identity_subjects :
    key => {
      name        = "${var.environment}-${key}-fic"
      identity_id = module.managed_identity.identity_ids[key]
      issuer      = module.aks.oidc_issuer_url
      subject     = subject
      audience    = ["api://AzureADTokenExchange"]
    }
  }
}

module "role_assignments" {
  source = "../../modules/role-assignments"
  role_assignments = merge(
    {
      acr_pull_kubelet = {
        scope                = module.acr.id
        role_definition_name = "AcrPull"
        principal_id         = module.managed_identity.principal_ids[var.aks.kubelet_identity_key]
      }
    },
    {
      for key, principal_id in module.managed_identity.principal_ids :
      "keyvault_${key}" => {
        scope                = module.keyvault.id
        role_definition_name = "Key Vault Secrets User"
        principal_id         = principal_id
      }
      if contains(keys(var.workload_service_accounts), key)
    },
    {
      for key, principal_id in module.managed_identity.principal_ids :
      "storage_${key}" => {
        scope                = module.storage.account_id
        role_definition_name = "Storage Blob Data Contributor"
        principal_id         = principal_id
      }
      if contains(keys(var.workload_service_accounts), key)
    },
    {
      for key, principal_id in module.managed_identity.principal_ids :
      "servicebus_${key}" => {
        scope                = module.servicebus.namespace_id
        role_definition_name = "Azure Service Bus Data Owner"
        principal_id         = principal_id
      }
      if contains(keys(var.workload_service_accounts), key)
    },
    {
      for key, principal_id in module.managed_identity.principal_ids :
      "search_${key}" => {
        scope                = module.ai_search.id
        role_definition_name = "Search Index Data Contributor"
        principal_id         = principal_id
      }
      if contains(keys(var.workload_service_accounts), key)
    },
    {
      for key, principal_id in module.managed_identity.principal_ids :
      "openai_${key}" => {
        scope                = module.openai.id
        role_definition_name = "Cognitive Services OpenAI User"
        principal_id         = principal_id
      }
      if contains(keys(var.workload_service_accounts), key)
    }
  )
}

output "helm_values" {
  description = "AKS integration values required by the FinsOpsIQ Helm chart."
  value = {
    namespace                      = var.helm_namespace
    acr_login_server               = module.acr.login_server
    key_vault_name                 = module.keyvault.name
    cosmos_endpoint                = module.cosmosdb.endpoint
    cosmos_database                = module.cosmosdb.database_name
    service_bus_namespace          = module.servicebus.namespace_name
    service_bus_topic              = module.servicebus.topic_name
    storage_blob_endpoint          = module.storage.primary_blob_endpoint
    storage_container              = module.storage.container_name
    applicationinsights_connection = module.application_insights.connection_string
    azure_search_endpoint          = module.ai_search.endpoint
    azure_openai_endpoint          = module.openai.endpoint
    azure_openai_deployment_names  = module.openai.deployment_names
    workload_identity_client_ids   = module.managed_identity.client_ids
    workload_identity_subjects     = module.workload_identity.subjects
  }
  sensitive = true
}

output "aks" {
  description = "AKS deployment outputs."
  value = {
    name                = module.aks.name
    id                  = module.aks.id
    oidc_issuer_url     = module.aks.oidc_issuer_url
    node_resource_group = module.aks.node_resource_group
  }
}
