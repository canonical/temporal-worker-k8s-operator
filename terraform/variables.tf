variable "name" {
  type        = string
  description = "Name of the deployed application"
  default     = "temporal-worker-k8s"
}

variable "units" {
  type        = number
  description = "Number of units to deploy with this name and configuration"
  default     = 1
}

variable "model" {
  type        = string
  description = "Juju model where the application is to be deployed"
}

variable "revision" {
  type        = number
  description = "Revision of the charm to deploy"
  default     = 23
}

variable "channel" {
  type        = string
  description = "Charmhub channel to deploy the charm from"
  default     = "latest/edge" # TODO: change to 1.0/edge
}

variable "image" {
  type = object({
    image    = string
    username = optional(string)
    password = optional(string)
  })
  description = "Details of the worker image"
}

variable "host" {
  type        = string
  description = "The hostname of the Temporal server"
  default     = ""
}

variable "queue" {
  type        = string
  description = "Temporal task queue that the worker should connect to"
  default     = ""
}

variable "namespace" {
  type        = string
  description = "Temporal namespace that the worker should connect to"
  default     = ""
}

variable "log_level" {
  type        = string
  description = "Log level of gunicorn"
  default     = "info"
}

variable "sentry_config" {
  type = object({
    dsn           = optional(string)
    release       = optional(string)
    environment   = optional(string)
    redact_params = optional(bool)
    sample_rate   = optional(number)
  })
  description = "Sentry related configurations"
  default = {
    dsn           = "",
    release       = "",
    environment   = "",
    redact_params = false,
    sample_rate   = 1.0
  }
}

variable "vault_secrets" {
  type = list(object({
    path = string
    name = string
    key  = string
  }))
  description = "Vault secrets to pass to the worker"
  default     = []
}

variable "juju_secrets" {
  type = list(object({
    secret_id = string
    name      = optional(string)
    key       = optional(string)
  }))
  description = "JUju secrets to pass to the worker"
  default     = []
}

variable "environment_variables" {
  type = list(object({
    name  = string
    value = string
  }))
  description = "Plaintext environment variables to pass to the worker"
  default     = []
}

variable "auth_secret_id" {
  type        = string
  description = "Juju secret ID containing authentication and encryption key parameters"
  default     = ""
}

variable "tls" {
  type = object({
    root_cas = string
  })
  description = "Certificate parameters to establish TLS communication"
  default = {
    root_cas = ""
  }
}

variable "db_name" {
  type        = string
  description = "Name of the database created when relating to the database charm"
  default     = ""
}
