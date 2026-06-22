variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "sku" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_container_registry" "this" {
  name                          = substr(lower(var.name), 0, 50)
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku                           = var.sku
  admin_enabled                 = false
  public_network_access_enabled = true
  anonymous_pull_enabled        = false
  tags                          = var.tags
}

output "id" { value = azurerm_container_registry.this.id }
output "login_server" { value = azurerm_container_registry.this.login_server }
