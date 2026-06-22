resource "azurerm_storage_account" "this" {
  name                            = var.account_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = var.account_tier
  account_replication_type        = var.account_replication_type
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = var.public_network_access_enabled
  min_tls_version                 = "TLS1_2"
  tags                            = var.tags
}

resource "azurerm_storage_container" "this" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}
