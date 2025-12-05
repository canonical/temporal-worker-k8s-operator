variable "app_name" {
  type        = string
  description = "Name of the deployed application"
  default     = "temporal-worker-k8s"
}

variable "units" {
  type        = number
  description = "Number of units to deploy with this name and configuration"
  default     = 1
}

variable "revision" {
  type        = number
  description = "Revision of the charm to deploy"
  default     = null
}

variable "channel" {
  type        = string
  description = "Charmhub channel to deploy the charm from"
  default     = "1.0/stable"
}

variable "constraints" {
  type        = string
  description = "Constraints to be used when deploying this application"
  default     = "arch=amd64"
}

variable "image" {
  type = object({
    image             = string
    image_repository  = optional(string, "")
    registry_username = optional(string, "")
    registry_password = optional(string, "")
  })
  description = "Details of the worker image"
}

variable "config" {
  type        = map(string)
  description = "Configurations to deploy this application with"
  default     = {}
}
