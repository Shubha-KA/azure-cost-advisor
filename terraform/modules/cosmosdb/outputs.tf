output "account_id" {
  description = "Cosmos DB account resource ID."
  value       = azurerm_cosmosdb_account.this.id
}

output "account_name" {
  description = "Cosmos DB account name."
  value       = azurerm_cosmosdb_account.this.name
}

output "endpoint" {
  description = "Cosmos DB endpoint."
  value       = azurerm_cosmosdb_account.this.endpoint
}

output "database_name" {
  description = "Cosmos DB SQL database name."
  value       = azurerm_cosmosdb_sql_database.this.name
}

output "container_names" {
  description = "Cosmos DB container names."
  value       = { for key, container in azurerm_cosmosdb_sql_container.this : key => container.name }
}
