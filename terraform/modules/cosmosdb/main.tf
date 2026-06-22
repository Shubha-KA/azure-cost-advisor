resource "azurerm_cosmosdb_account" "this" {
  name                          = var.account_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = var.public_network_access_enabled
  local_authentication_disabled = var.local_authentication_disabled
  free_tier_enabled             = var.free_tier_enabled
  tags                          = var.tags

  consistency_policy {
    consistency_level = var.consistency_level
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = var.database_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
  throughput          = var.database_throughput
}

resource "azurerm_cosmosdb_sql_container" "this" {
  for_each = var.containers

  name                = each.value.name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths = each.value.partition_key_paths
  throughput          = each.value.throughput
}
