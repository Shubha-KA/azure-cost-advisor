variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "private_dns_zone_ids" { type = map(string) }
variable "cosmos_account_id" { type = string }
variable "storage_account_id" { type = string }
variable "key_vault_id" { type = string }
variable "registry_id" { type = string }
variable "search_service_id" { type = string }
variable "openai_account_id" { type = string }
variable "tags" { type = map(string) }

locals {
  endpoints = {
    cosmos = {
      resource_id = var.cosmos_account_id
      subresource = "Sql"
    }
    blob = {
      resource_id = var.storage_account_id
      subresource = "blob"
    }
    vault = {
      resource_id = var.key_vault_id
      subresource = "vault"
    }
    acr = {
      resource_id = var.registry_id
      subresource = "registry"
    }
    search = {
      resource_id = var.search_service_id
      subresource = "searchService"
    }
    openai = {
      resource_id = var.openai_account_id
      subresource = "account"
    }
  }
}

resource "azurerm_private_endpoint" "this" {
  for_each = local.endpoints

  name                = "pe-${var.name}-${each.key}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.name}-${each.key}"
    private_connection_resource_id = each.value.resource_id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [var.private_dns_zone_ids[each.key]]
  }
}
