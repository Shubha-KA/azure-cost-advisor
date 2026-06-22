output "id" {
  description = "Application Insights resource ID."
  value       = azurerm_application_insights.this.id
}

output "name" {
  description = "Application Insights name."
  value       = azurerm_application_insights.this.name
}

output "connection_string" {
  description = "Application Insights connection string."
  value       = azurerm_application_insights.this.connection_string
  sensitive   = true
}
