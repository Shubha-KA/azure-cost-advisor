variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "retention_days" { type = number }
variable "tags" { type = map(string) }

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_days
  daily_quota_gb      = 1
  tags                = var.tags
}

resource "azurerm_application_insights" "this" {
  name                 = "appi-${var.name}"
  location             = var.location
  resource_group_name  = var.resource_group_name
  workspace_id         = azurerm_log_analytics_workspace.this.id
  application_type     = "web"
  daily_data_cap_in_gb = 1
  retention_in_days    = var.retention_days
  tags                 = var.tags
}

output "log_analytics_workspace_id" { value = azurerm_log_analytics_workspace.this.id }
output "application_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}
