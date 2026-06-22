output "namespace_id" {
  description = "Service Bus namespace resource ID."
  value       = azurerm_servicebus_namespace.this.id
}

output "namespace_name" {
  description = "Service Bus namespace name."
  value       = azurerm_servicebus_namespace.this.name
}

output "topic_id" {
  description = "Service Bus topic resource ID."
  value       = azurerm_servicebus_topic.this.id
}

output "topic_name" {
  description = "Service Bus topic name."
  value       = azurerm_servicebus_topic.this.name
}
