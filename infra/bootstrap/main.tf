resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  prefix = "${var.project_name}-tfstate"
  tags = merge(var.tags, {
    application = "azure-cost-advisor"
    workload    = "terraform-state"
    managed_by  = "terraform-bootstrap"
  })
}

resource "azurerm_resource_group" "state" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_role_assignment" "state_data_resource_group" {
  for_each = var.terraform_principal_object_ids

  scope                = azurerm_resource_group.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
}

resource "azurerm_storage_account" "state" {
  # checkov:skip=CKV_AZURE_33:Queue service not used for tfstate
  # checkov:skip=CKV_AZURE_206:ZRS replication is sufficient for tfstate
  # checkov:skip=CKV2_AZURE_1:CMK not required for bootstrap tfstate
  name                             = substr("st${var.project_name}tf${random_string.suffix.result}", 0, 24)
  resource_group_name              = azurerm_resource_group.state.name
  location                         = var.location
  account_tier                     = "Standard"
  account_replication_type         = "ZRS"
  min_tls_version                  = "TLS1_2"
  shared_access_key_enabled        = false
  public_network_access_enabled    = false
  allow_nested_items_to_be_public  = false
  cross_tenant_replication_enabled = false
  default_to_oauth_authentication  = true

  blob_properties {
    versioning_enabled  = true
    change_feed_enabled = true

    delete_retention_policy {
      days = 30
    }

    container_delete_retention_policy {
      days = 30
    }

    restore_policy {
      days = 29
    }
  }

  tags = local.tags

  depends_on = [azurerm_role_assignment.state_data_resource_group]
}

resource "azurerm_storage_container" "state" {
  # checkov:skip=CKV2_AZURE_21:Blob logging is not required for tfstate container
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

resource "azurerm_virtual_network" "state" {
  name                = "vnet-${local.prefix}"
  resource_group_name = azurerm_resource_group.state.name
  location            = var.location
  address_space       = var.address_space
  tags                = local.tags
}

resource "azurerm_subnet" "private_endpoints" {
  # checkov:skip=CKV2_AZURE_31:NSG not required for private endpoint subnet
  name                              = "snet-private-endpoints"
  resource_group_name               = azurerm_resource_group.state.name
  virtual_network_name              = azurerm_virtual_network.state.name
  address_prefixes                  = [var.private_endpoint_subnet_prefix]
  private_endpoint_network_policies = "Disabled"
}

resource "azurerm_private_dns_zone" "blob" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = azurerm_resource_group.state.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob" {
  name                  = "terraform-state-blob-link"
  resource_group_name   = azurerm_resource_group.state.name
  private_dns_zone_name = azurerm_private_dns_zone.blob.name
  virtual_network_id    = azurerm_virtual_network.state.id
  registration_enabled  = false
  tags                  = local.tags
}

resource "azurerm_private_endpoint" "state_blob" {
  name                = "pe-${local.prefix}-blob"
  resource_group_name = azurerm_resource_group.state.name
  location            = var.location
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "terraform-state-blob"
    private_connection_resource_id = azurerm_storage_account.state.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }
}

resource "azurerm_role_assignment" "state_data" {
  for_each = var.terraform_principal_object_ids

  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
}

resource "azurerm_management_lock" "resource_group" {
  name       = "terraform-state-resource-group-delete-lock"
  scope      = azurerm_resource_group.state.id
  lock_level = "CanNotDelete"
  notes      = "Protects the Terraform remote-state resource group from deletion."

  depends_on = [azurerm_private_endpoint.state_blob]
}

resource "azurerm_management_lock" "storage_account" {
  name       = "terraform-state-storage-delete-lock"
  scope      = azurerm_storage_account.state.id
  lock_level = "CanNotDelete"
  notes      = "Protects the Terraform remote-state account from deletion."
}

resource "azurerm_management_lock" "container" {
  name       = "terraform-state-container-delete-lock"
  scope      = azurerm_storage_container.state.id
  lock_level = "CanNotDelete"
  notes      = "Protects the Terraform state container from deletion."
}
