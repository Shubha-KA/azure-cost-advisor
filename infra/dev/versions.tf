terraform {
  required_version = ">= 1.7.0"

  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id     = var.subscription_id
  tenant_id           = var.platform_tenant_id
  storage_use_azuread = true
}

provider "azuread" {
  tenant_id = var.platform_tenant_id
}
