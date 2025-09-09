output "name" {
  value = juju_application.temporal_worker_k8s.name
}

output "provides" {
  value = {
    metrics_endpoint  = "metrics-endpoint"
    grafana_dashboard = "grafana-dashboard"
  }
}

output "requires" {
  value = {
    logging  = "logging"
    vault    = "vault"
    database = "postgresql_client"
  }
}
