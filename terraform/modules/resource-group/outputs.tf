output "name" {
  description = "Resource group name."
  value       = azurerm_resource_group.this.name
}

output "location" {
  description = "Resource group location."
  value       = azurerm_resource_group.this.location
}

output "id" {
  description = "Resource group resource ID."
  value       = azurerm_resource_group.this.id
}

output "tags" {
  description = "Effective tags."
  value       = azurerm_resource_group.this.tags
}
