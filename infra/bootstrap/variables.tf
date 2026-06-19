variable "subscription_id" {
  type        = string
  description = "Azure subscription that owns the Terraform state resources."
}

variable "tenant_id" {
  type        = string
  description = "Microsoft Entra tenant used by the Terraform deployment identity."
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "project_name" {
  type    = string
  default = "finops"
}

variable "address_space" {
  type    = list(string)
  default = ["10.60.0.0/24"]
}

variable "private_endpoint_subnet_prefix" {
  type    = string
  default = "10.60.0.0/27"
}

variable "environments" {
  type    = set(string)
  default = ["dev"]
}

variable "terraform_principal_object_ids" {
  type        = set(string)
  description = "Object IDs allowed to read, write, and lease Terraform state blobs."
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "storage_account_suffix" {
  type        = string
  description = "A stable suffix for the storage account to prevent random replacement."
  default     = ""
}

