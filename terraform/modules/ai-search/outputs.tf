output "id" {
  description = "Search service resource ID."
  value       = azurerm_search_service.this.id
}

output "name" {
  description = "Search service name."
  value       = azurerm_search_service.this.name
}

output "endpoint" {
  description = "Search endpoint."
  value       = "https://${azurerm_search_service.this.name}.search.windows.net"
}

output "principal_id" {
  description = "Search system-assigned identity principal ID."
  value       = azurerm_search_service.this.identity[0].principal_id
}
