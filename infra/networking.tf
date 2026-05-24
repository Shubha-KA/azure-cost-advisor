# =============================================================================
# Hub-and-Spoke Network Topology
#
#   Internet → Application Gateway (Hub VNet — 10.0.0.0/16)
#                    ↓ VNet Peering
#              Spoke VNet (10.1.0.0/16)
#                └── snet-vmss (10.1.2.0/24) → VMSS (Streamlit :8501)
# =============================================================================

# -----------------------------------------------------------------------------
# Hub VNet — public entry via Application Gateway
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "hub" {
  name                = "vnet-${var.project_name}-hub-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = var.hub_vnet_address_space
  tags                = var.tags
}

resource "azurerm_subnet" "hub_appgw" {
  name                 = "snet-appgw"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_appgw_subnet_prefix]
}

# -----------------------------------------------------------------------------
# Spoke VNet — VMSS (Streamlit)
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "spoke" {
  name                = "vnet-${var.project_name}-spoke-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = var.spoke_vnet_address_space
  tags                = var.tags
}

resource "azurerm_subnet" "spoke_vmss" {
  name                 = "snet-vmss"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_vmss_subnet_prefix]
}

# -----------------------------------------------------------------------------
# VNet Peering — Hub ↔ Spoke (bidirectional)
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                      = "peer-hub-to-spoke"
  resource_group_name       = azurerm_resource_group.main.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.spoke.id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
  use_remote_gateways          = false
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                      = "peer-spoke-to-hub"
  resource_group_name       = azurerm_resource_group.main.name
  virtual_network_name      = azurerm_virtual_network.spoke.name
  remote_virtual_network_id = azurerm_virtual_network.hub.id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
  use_remote_gateways          = false
}

# -----------------------------------------------------------------------------
# NSG — Application Gateway subnet (Hub)
# -----------------------------------------------------------------------------
resource "azurerm_network_security_group" "hub_appgw" {
  name                = "nsg-hub-appgw-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags

  security_rule {
    name                       = "Allow-HTTP-Inbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-HTTPS-Inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-AppGw-Management"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "65200-65535"
    source_address_prefix      = "GatewayManager"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-Outbound-To-Spoke"
    priority                   = 200
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.streamlit_port)
    source_address_prefix      = var.hub_vnet_address_space[0]
    destination_address_prefix = var.spoke_vnet_address_space[0]
  }
}

resource "azurerm_subnet_network_security_group_association" "hub_appgw" {
  subnet_id                 = azurerm_subnet.hub_appgw.id
  network_security_group_id = azurerm_network_security_group.hub_appgw.id
}

# -----------------------------------------------------------------------------
# NSG — VMSS subnet (Spoke)
# -----------------------------------------------------------------------------
resource "azurerm_network_security_group" "spoke_vmss" {
  name                = "nsg-spoke-vmss-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags

  security_rule {
    name                       = "Allow-Streamlit-From-Hub"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.streamlit_port)
    source_address_prefix      = var.hub_vnet_address_space[0]
    destination_address_prefix = var.spoke_vmss_subnet_prefix
  }

  security_rule {
    name                       = "Allow-AppGw-HealthProbe"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.streamlit_port)
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-Outbound-Internet"
    priority                   = 200
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = var.spoke_vmss_subnet_prefix
    destination_address_prefix = "Internet"
  }

  security_rule {
    name                       = "Allow-Outbound-HTTP"
    priority                   = 210
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = var.spoke_vmss_subnet_prefix
    destination_address_prefix = "Internet"
  }
}

resource "azurerm_subnet_network_security_group_association" "spoke_vmss" {
  subnet_id                 = azurerm_subnet.spoke_vmss.id
  network_security_group_id = azurerm_network_security_group.spoke_vmss.id
}

# -----------------------------------------------------------------------------
# Public IP — Application Gateway frontend
# -----------------------------------------------------------------------------
resource "azurerm_public_ip" "appgw" {
  name                = "pip-appgw-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}
