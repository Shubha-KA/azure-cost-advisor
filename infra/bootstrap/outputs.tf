output "resource_group_name" {
  value = azurerm_resource_group.state.name
}

output "storage_account_name" {
  value = azurerm_storage_account.state.name
}

output "container_name" {
  value = azurerm_storage_container.state.name
}

output "state_vnet_id" {
  value = azurerm_virtual_network.state.id
}

output "state_private_endpoint_ip" {
  value = azurerm_private_endpoint.state_blob.private_service_connection[0].private_ip_address
}

output "backend_configuration" {
  value = {
    resource_group_name  = azurerm_resource_group.state.name
    storage_account_name = azurerm_storage_account.state.name
    container_name       = azurerm_storage_container.state.name
    use_azuread_auth     = true
    keys = {
      for environment in var.environments :
      environment => "${environment}/aks-platform.tfstate"
    }
  }
}
