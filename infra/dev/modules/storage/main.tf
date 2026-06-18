variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "replication_type" { type = string }
variable "public_network_access_enabled" { type = bool }
variable "tags" { type = map(string) }

resource "azurerm_storage_account" "this" {
  name                            = substr(lower(var.name), 0, 24)
  location                        = var.location
  resource_group_name             = var.resource_group_name
  account_tier                    = "Standard"
  account_replication_type        = var.replication_type
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  public_network_access_enabled   = var.public_network_access_enabled
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
    container_delete_retention_policy {
      days = 30
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "raw" {
  name                  = "finops-raw"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

output "id" { value = azurerm_storage_account.this.id }
output "account_url" { value = azurerm_storage_account.this.primary_blob_endpoint }
output "container_name" { value = azurerm_storage_container.raw.name }
