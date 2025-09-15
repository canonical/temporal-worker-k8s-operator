resource "juju_application" "temporal_worker_k8s" {
  name  = var.app_name
  model = var.model

  charm {
    name     = "temporal-worker-k8s"
    revision = var.revision
    channel  = var.channel
  }

  constraints = var.constraints
  config      = var.config

  units = var.units
}


resource "null_resource" "attach_image" {
  provisioner "local-exec" {
    command = <<EOT
      echo "${yamlencode({
    "registrypath" = var.image.image,
    "username"     = var.image.registry_username,
    "password"     = var.image.registry_password,
})}" > temporal_worker_image.yaml

      juju attach-resource ${var.app_name} temporal-worker-image=temporal_worker_image.yaml

      rm temporal_worker_image.yaml
    EOT
}

depends_on = [resource.juju_application.temporal_worker_k8s]

triggers = {
  image = jsonencode(var.image)
}
}
