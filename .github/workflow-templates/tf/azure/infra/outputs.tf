output "resource_group_name" {
  description = "Name of the validation resource group"
  value       = azurerm_resource_group.validation.name
}

output "resource_group_location" {
  description = "Location of the validation resource group"
  value       = azurerm_resource_group.validation.location
}