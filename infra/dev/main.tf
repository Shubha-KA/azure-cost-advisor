resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

module "network" {
  source = "./modules/network"

  name                              = local.prefix
  location                          = var.location
  resource_group_name               = azurerm_resource_group.this.name
  address_space                     = var.address_space
  aks_subnet_prefix                 = var.aks_subnet_prefix
  application_gateway_subnet_prefix = var.application_gateway_subnet_prefix
  private_endpoint_subnet_prefix    = var.private_endpoint_subnet_prefix
  create_private_endpoints          = var.create_private_endpoints
  private_dns_zones                 = local.private_dns_zones
  tags                              = local.tags
}

module "monitoring" {
  source = "./modules/monitoring"

  name                = local.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  retention_days      = var.log_retention_days
  tags                = local.tags
}

module "identities" {
  source = "./modules/identities"

  names               = local.workload_names
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "registry" {
  source = "./modules/registry"

  name                = "acr${var.project_name}${var.environment}${random_string.suffix.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Basic"
  tags                = local.tags
}

module "key_vault" {
  source = "./modules/key-vault"

  name                          = "kv-${var.project_name}-${var.environment}-${random_string.suffix.result}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = var.platform_tenant_id
  public_network_access_enabled = !var.create_private_endpoints
  tags                          = local.tags
}

module "storage" {
  source = "./modules/storage"

  name                          = "st${var.project_name}${var.environment}${random_string.suffix.result}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  replication_type              = "LRS"
  public_network_access_enabled = !var.create_private_endpoints
  tags                          = local.tags
}

module "cosmos" {
  source = "./modules/cosmos-nosql"

  name                          = "cosmos-${local.prefix}-${random_string.suffix.result}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  serverless                    = var.cosmos_serverless
  max_throughput                = var.cosmos_max_throughput
  public_network_access_enabled = !var.create_private_endpoints
  containers                    = local.cosmos_containers
  tags                          = local.tags
}

module "service_bus" {
  source = "./modules/service-bus"

  name                = "sb-${local.prefix}-${random_string.suffix.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "search" {
  source = "./modules/ai-search"

  name                          = "search-${local.prefix}-${random_string.suffix.result}"
  location                      = var.search_location != "" ? var.search_location : var.location
  resource_group_name           = azurerm_resource_group.this.name
  sku                           = var.search_sku
  public_network_access_enabled = !var.create_private_endpoints
  tags                          = local.tags
}

data "azurerm_cognitive_account" "openai" {
  name                = var.existing_openai_account_name
  resource_group_name = var.existing_openai_resource_group_name
}

module "application_gateway" {
  source = "./modules/application-gateway"

  name                = local.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = module.network.application_gateway_subnet_id
  capacity            = var.application_gateway_capacity
  tags                = local.tags
}

module "aks" {
  source = "./modules/aks"

  name                          = "aks-${local.prefix}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  resource_group_id             = azurerm_resource_group.this.id
  dns_prefix                    = "${local.prefix}-${random_string.suffix.result}"
  subnet_id                     = module.network.aks_subnet_id
  private_cluster_enabled       = var.private_cluster_enabled
  system_node_vm_size           = var.system_node_vm_size
  system_node_count             = var.system_node_count
  system_node_min_count         = var.system_node_min_count
  system_node_max_count         = var.system_node_max_count
  log_analytics_workspace_id    = module.monitoring.log_analytics_workspace_id
  admin_group_object_ids        = var.admin_group_object_ids
  application_gateway_id        = module.application_gateway.id
  application_gateway_subnet_id = module.network.application_gateway_subnet_id
  tags                          = local.tags
}

module "rbac" {
  source = "./modules/rbac"

  workload_principal_ids     = module.identities.principal_ids
  acr_id                     = module.registry.id
  key_vault_id               = module.key_vault.id
  storage_account_id         = module.storage.id
  cosmos_account_id          = module.cosmos.id
  cosmos_sql_database_scope  = module.cosmos.sql_database_scope
  service_bus_namespace_id   = module.service_bus.id
  search_service_id          = module.search.id
  openai_account_id          = data.azurerm_cognitive_account.openai.id
  kubelet_identity_object_id = module.aks.kubelet_identity_object_id
}

resource "azurerm_federated_identity_credential" "workload" {
  for_each = local.workload_service_accounts

  name      = "fic-${each.key}"
  parent_id = module.identities.ids[each.key]
  audience  = ["api://AzureADTokenExchange"]
  issuer    = module.aks.oidc_issuer_url
  subject   = "system:serviceaccount:${each.value.namespace}:${each.value.service_account}"
}

resource "azurerm_role_assignment" "aks_admin" {
  for_each = var.aks_admin_principal_ids

  scope                = module.aks.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = each.value
}

module "private_endpoints" {
  count  = var.create_private_endpoints ? 1 : 0
  source = "./modules/private-endpoints"

  name                 = local.prefix
  location             = var.location
  resource_group_name  = azurerm_resource_group.this.name
  subnet_id            = module.network.private_endpoint_subnet_id
  private_dns_zone_ids = module.network.private_dns_zone_ids
  cosmos_account_id    = module.cosmos.id
  storage_account_id   = module.storage.id
  key_vault_id         = module.key_vault.id
  registry_id          = module.registry.id
  search_service_id    = module.search.id
  openai_account_id    = data.azurerm_cognitive_account.openai.id
  tags                 = local.tags
}
