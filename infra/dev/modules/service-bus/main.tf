variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_servicebus_namespace" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku                           = "Standard"
  local_auth_enabled            = false
  public_network_access_enabled = true
  minimum_tls_version           = "1.2"
  tags                          = var.tags
}

resource "azurerm_servicebus_topic" "events" {
  name                                    = "finops-events"
  namespace_id                            = azurerm_servicebus_namespace.this.id
  partitioning_enabled                    = true
  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = "PT10M"
  support_ordering                        = false
  default_message_ttl                     = "P7D"
}

resource "azurerm_servicebus_subscription" "consumer" {
  for_each = toset([
    "processing-service",
    "ai-service",
    "notification-service",
  ])

  name                                 = each.key
  topic_id                             = azurerm_servicebus_topic.events.id
  max_delivery_count                   = 5
  dead_lettering_on_message_expiration = true
  default_message_ttl                  = "P7D"
}

output "id" { value = azurerm_servicebus_namespace.this.id }
output "namespace_fqdn" { value = "${azurerm_servicebus_namespace.this.name}.servicebus.windows.net" }
