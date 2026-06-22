output "vnet_id" {
  description = "Virtual network resource ID."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Virtual network name."
  value       = azurerm_virtual_network.this.name
}

output "subnet_ids" {
  description = "Subnet IDs keyed by logical name."
  value       = { for key, subnet in azurerm_subnet.this : key => subnet.id }
}

output "subnet_names" {
  description = "Subnet names keyed by logical name."
  value       = { for key, subnet in azurerm_subnet.this : key => subnet.name }
}
