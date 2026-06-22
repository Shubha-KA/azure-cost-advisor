variable "names" { type = set(string) }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_user_assigned_identity" "this" {
  for_each = var.names

  name                = "id-${each.key}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

output "ids" {
  value = { for key, identity in azurerm_user_assigned_identity.this : key => identity.id }
}

output "principal_ids" {
  value = { for key, identity in azurerm_user_assigned_identity.this : key => identity.principal_id }
}

output "client_ids" {
  value = { for key, identity in azurerm_user_assigned_identity.this : key => identity.client_id }
}
