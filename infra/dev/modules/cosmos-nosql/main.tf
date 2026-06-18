variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "serverless" { type = bool }
variable "max_throughput" { type = number }
variable "public_network_access_enabled" { type = bool }
variable "containers" { type = map(any) }
variable "tags" { type = map(string) }

resource "azurerm_cosmosdb_account" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = var.public_network_access_enabled
  local_authentication_disabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  dynamic "capabilities" {
    for_each = var.serverless ? [1] : []
    content {
      name = "EnableServerless"
    }
  }

  backup {
    type = "Continuous"
    tier = "Continuous30Days"
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = "finops"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name

  dynamic "autoscale_settings" {
    for_each = var.serverless ? [] : [1]
    content {
      max_throughput = var.max_throughput
    }
  }
}

resource "azurerm_cosmosdb_sql_container" "this" {
  for_each = var.containers

  name                  = each.key
  resource_group_name   = var.resource_group_name
  account_name          = azurerm_cosmosdb_account.this.name
  database_name         = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths   = ["/tenantId"]
  partition_key_version = 2

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }

    excluded_path {
      path = "/metadataJson/?"
    }

    excluded_path {
      path = "/evidence/*"
    }

    excluded_path {
      path = "/content/?"
    }
  }
}

output "id" { value = azurerm_cosmosdb_account.this.id }
output "endpoint" { value = azurerm_cosmosdb_account.this.endpoint }
output "database_name" { value = azurerm_cosmosdb_sql_database.this.name }
output "sql_database_scope" { value = "${azurerm_cosmosdb_account.this.id}/dbs/${azurerm_cosmosdb_sql_database.this.name}" }
