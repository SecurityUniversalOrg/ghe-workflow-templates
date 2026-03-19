provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "validation" {
  name     = "${var.resource_group_name_prefix}-${terraform.workspace}"
  location = var.location

  tags = {
    environment = terraform.workspace
    managed_by  = "terraform"
    purpose     = "workflow-validation"
  }
}