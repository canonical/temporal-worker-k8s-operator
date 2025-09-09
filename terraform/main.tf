resource "juju_application" "temporal_worker_k8s" {
  name  = var.name
  model = var.model

  charm {
    name     = "temporal-worker-k8s"
    revision = var.revision
    channel  = var.channel
  }

  config = {
    host      = var.host
    queue     = var.queue
    namespace = var.namespace

    log-level = var.log_level

    environment = yamlencode({
      "env"   = var.environment_variables,
      "juju"  = var.juju_secrets,
      "vault" = var.vault_secrets,
    })

    sentry-dsn           = var.sentry_config["dsn"]
    sentry-release       = var.sentry_config["release"]
    sentry-environment   = var.sentry_config["environment"]
    sentry-redact-params = var.sentry_config["redact_params"]
    sentry-sample-rate   = var.sentry_config["sample_rate"]

    auth-secret-id = var.auth_secret_id

    tls-root-cas = var.tls.root_cas

    db-name = var.db_name
  }

  units = var.units
}


resource "null_resource" "attach_image" {
  provisioner "local-exec" {
    command = <<EOT
      echo "${yamlencode({
    "registrypath" = var.image.image,
    "username"     = var.image.username,
    "password"     = var.image.password,
})}" > temporal_worker_image.yaml

      juju attach-resource ${var.name} temporal-worker-image=temporal_worker_image.yaml

      rm temporal_worker_image.yaml
    EOT
}

depends_on = [resource.juju_application.temporal_worker_k8s]

triggers = {
  image = jsonencode(var.image)
}
}
