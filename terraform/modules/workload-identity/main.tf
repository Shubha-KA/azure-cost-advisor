resource "azurerm_federated_identity_credential" "this" {
  for_each = var.federated_credentials

  name                = each.value.name
  resource_group_name = var.resource_group_name
  parent_id           = each.value.identity_id
  audience            = each.value.audience
  issuer              = each.value.issuer
  subject             = each.value.subject
}
