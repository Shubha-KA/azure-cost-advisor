resource "azurerm_application_insights" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  workspace_id        = var.workspace_id
  application_type    = var.application_type
  tags                = var.tags
}
