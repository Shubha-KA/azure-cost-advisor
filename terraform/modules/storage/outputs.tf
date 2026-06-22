output "account_id" {
  description = "Storage account resource ID."
  value       = azurerm_storage_account.this.id
}

output "account_name" {
  description = "Storage account name."
  value       = azurerm_storage_account.this.name
}

output "primary_blob_endpoint" {
  description = "Storage account primary blob endpoint."
  value       = azurerm_storage_account.this.primary_blob_endpoint
}

output "container_name" {
  description = "Blob container name."
  value       = azurerm_storage_container.this.name
}
