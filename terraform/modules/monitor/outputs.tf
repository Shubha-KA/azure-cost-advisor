output "id" {
  description = "Log Analytics workspace ID."
  value       = azurerm_log_analytics_workspace.this.id
}

output "workspace_id" {
  description = "Log Analytics workspace customer ID."
  value       = azurerm_log_analytics_workspace.this.workspace_id
}

output "name" {
  description = "Log Analytics workspace name."
  value       = azurerm_log_analytics_workspace.this.name
}
