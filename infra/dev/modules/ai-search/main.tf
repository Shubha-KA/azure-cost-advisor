variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "sku" { type = string }
variable "public_network_access_enabled" { type = bool }
variable "tags" { type = map(string) }

resource "azurerm_search_service" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku                           = var.sku
  replica_count                 = 1
  partition_count               = 1
  local_authentication_enabled  = false
  public_network_access_enabled = var.public_network_access_enabled
  semantic_search_sku           = var.sku == "free" ? "free" : "standard"

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

output "id" { value = azurerm_search_service.this.id }
output "endpoint" { value = "https://${azurerm_search_service.this.name}.search.windows.net" }
