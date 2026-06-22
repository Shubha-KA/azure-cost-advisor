variable "workload_principal_ids" { type = map(string) }
variable "acr_id" { type = string }
variable "key_vault_id" { type = string }
variable "storage_account_id" { type = string }
variable "cosmos_account_id" { type = string }
variable "cosmos_sql_database_scope" { type = string }
variable "service_bus_namespace_id" { type = string }
variable "search_service_id" { type = string }
variable "openai_account_id" { type = string }
variable "kubelet_identity_object_id" { type = string }

resource "azurerm_role_assignment" "kubelet_acr" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = var.kubelet_identity_object_id
}

resource "azurerm_role_assignment" "key_vault" {
  for_each = var.workload_principal_ids

  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "blob_collection" {
  for_each = {
    for name, principal_id in var.workload_principal_ids :
    name => principal_id if name != "frontend"
  }

  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
}

resource "azurerm_cosmosdb_sql_role_assignment" "data_contributor" {
  for_each = {
    "auth-service"         = var.workload_principal_ids["auth-service"]
    "api-gateway"          = var.workload_principal_ids["api-gateway"]
    "collection-service"   = var.workload_principal_ids["collection-service"]
    "processing-service"   = var.workload_principal_ids["processing-service"]
    "ai-service"           = var.workload_principal_ids["ai-service"]
    "notification-service" = var.workload_principal_ids["notification-service"]
  }

  resource_group_name = split("/", var.cosmos_account_id)[4]
  account_name        = split("/", var.cosmos_account_id)[8]
  role_definition_id  = "${var.cosmos_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = each.value
  scope               = var.cosmos_sql_database_scope
}

resource "azurerm_role_assignment" "service_bus_sender" {
  for_each = {
    "auth-service"       = var.workload_principal_ids["auth-service"]
    "collection-service" = var.workload_principal_ids["collection-service"]
    "processing-service" = var.workload_principal_ids["processing-service"]
    "ai-service"         = var.workload_principal_ids["ai-service"]
  }

  scope                = var.service_bus_namespace_id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "service_bus_receiver" {
  for_each = {
    "processing-service"   = var.workload_principal_ids["processing-service"]
    "ai-service"           = var.workload_principal_ids["ai-service"]
    "notification-service" = var.workload_principal_ids["notification-service"]
  }

  scope                = var.service_bus_namespace_id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "search_index_data" {
  scope                = var.search_service_id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = var.workload_principal_ids["ai-service"]
}

resource "azurerm_role_assignment" "search_service" {
  scope                = var.search_service_id
  role_definition_name = "Search Service Contributor"
  principal_id         = var.workload_principal_ids["ai-service"]
}

resource "azurerm_role_assignment" "openai" {
  scope                = var.openai_account_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.workload_principal_ids["ai-service"]
}
