output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "aks_cluster_name" {
  value = module.aks.name
}

output "application_gateway_public_ip" {
  value = module.application_gateway.public_ip_address
}

output "acr_login_server" {
  value = module.registry.login_server
}

output "cosmos_endpoint" {
  value = module.cosmos.endpoint
}

output "storage_account_url" {
  value = module.storage.account_url
}

output "service_bus_namespace" {
  value = module.service_bus.namespace_fqdn
}

output "search_endpoint" {
  value = module.search.endpoint
}

output "openai_endpoint" {
  value = data.azurerm_cognitive_account.openai.endpoint
}

output "application_insights_connection_string" {
  value     = module.monitoring.application_insights_connection_string
  sensitive = true
}

output "workload_identity_client_ids" {
  value = module.identities.client_ids
}

output "key_vault_name" {
  value = split("/", module.key_vault.id)[8]
}

output "key_vault_uri" {
  value = module.key_vault.vault_uri
}

output "platform_tenant_id" {
  value = var.platform_tenant_id
}

output "entra_login_client_id" {
  value = azuread_application.login.client_id
}

output "entra_collection_client_id" {
  value = azuread_application.collection.client_id
}
