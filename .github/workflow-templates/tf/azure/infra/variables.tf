variable "location" {
  description = "Azure region for the test deployment"
  type        = string
  default     = "eastus2"
}

variable "resource_group_name_prefix" {
  description = "Prefix for the validation resource group"
  type        = string
  default     = "rg-tf-validate"
}