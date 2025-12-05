data "juju_model" "terraform" {
  name  = "terraform"
  owner = "admin"
}

resource "juju_application" "temporal_worker_k8s" {
  name = var.app_name
  model_uuid = data.juju_model.terraform.uuid

  charm {
    name     = "temporal-worker-k8s"
    revision = var.revision
    channel  = var.channel
  }

  constraints = var.constraints
  config      = var.config

  resources = var.image.image != "" ? {
    "temporal-worker-image" = var.image.image
  } : {}

  registry_credentials = {
    (var.image.image_repository) = {
      username = var.image.registry_username
      password = var.image.registry_password
    }
  }

  units = var.units
}
