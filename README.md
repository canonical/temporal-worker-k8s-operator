[![Charmhub Badge](https://charmhub.io/temporal-worker-k8s/badge.svg)](https://charmhub.io/temporal-worker-k8s)
[![Release Edge](https://github.com/canonical/temporal-worker-k8s-operator/actions/workflows/test_and_publish_charm.yaml/badge.svg)](https://github.com/canonical/temporal-worker-k8s-operator/actions/workflows/test_and_publish_charm.yaml)

# Temporal Worker K8s Operator

This is the Kubernetes Python Operator for the Temporal Worker.

## Description

Temporal is a developer-first, open source platform that ensures the successful
execution of services and applications (using workflows).

Use Workflow as Code (TM) to build and operate resilient applications. Leverage
developer friendly primitives and avoid fighting your infrastructure

This operator provides a Temporal Worker, and consists of Python scripts which
connect to a deployed Temporal server.

## Usage

### Deploying

To deploy the Charmed Temporal Worker, you can start by creating a Temporal
workflow, or use the one provided in
[`resource_sample_py`](./resource_sample_py/). Once done, the project can be
built as a [ROCK](https://documentation.ubuntu.com/rockcraft/en/stable/) and
pushed to the [local registry](https://microk8s.io/docs/registry-built-in) by
running the following command inside the `resource_sample_py` directory:

```bash
make -C resource_sample_py build_rock
```

The Charmed Temporal Worker can then be deployed and connected to a deployed
Temporal server using the Juju command line as follows:

```bash
juju deploy temporal-worker-k8s --resource temporal-worker-image=localhost:32000/temporal-worker-rock
juju config temporal-worker-k8s --file=path/to/config.yaml
```

#### **`config.yaml`**

```yaml
temporal-worker-k8s:
  host: "localhost:7233" # Replace with Temporal server hostname
  queue: "test-queue"
  namespace: "test"
```

Once done, the charm should enter an active state, indicating that the worker is
running successfully. To verify this, you can check the logs of the juju unit to
ensure there are no errors with the workload container:

```bash
juju ssh --container temporal-worker temporal-worker-k8s/0 /charm/bin/pebble logs temporal-worker -f
```

Note: The only requirement for the ROCK is to have a `scripts/start-worker.sh`
file, which will be used as the entry point for the charm to start the workload
container.

### Adding Secrets & Environment Variables

The Charmed Temporal Worker allows the user to configure multiple sources of
environment variables and secrets to be injected into the workload container and
consumed by the user's workflow definitions. These sources can be configured
through the `environment` config parameter of the charm. Below are the three
sources of environment variables and secrets currently supported. A user may
choose to use one, all or none of them. Once the `environment.yaml` file is
ready, it can be configured into the charm as follows:

```bash
juju config temporal-worker-k8s environment=@/path/to/environment.yaml
```

These environment variables can then be retrieved by the workflows by using the
`os` package as follows:

```python
import os
value1 = os.getenv("key1")
```

#### Direct Environment Variables

These are usually values that are not secret and can be stored as plaintext. An
example is setting the application environment to `staging` or `production`.
They can be set as follows:

##### **`environment.yaml`**

```yaml
environment:
  env:
    - key1: value1
    - key2: value2
```

#### Juju User Secrets (Requires Juju 3.3+)

[Juju secrets](https://juju.is/docs/juju/manage-secrets) are values which can be
stored in the model and accessed by the charm. To do so, you must first add the
secret and grant the charm access to it:

```bash
juju add-secret my-secret key1=value1 key2=value2

# Output: secret:<secret_id>

juju grant-secret my-secret temporal-worker-k8s
```

The environment variables can then be configured into the charm as follows:

##### **`environment.yaml`**

```yaml
environment:
  juju:
    - secret-id: <secret_id>
      key: key1
    - secret-id: <secret_id>
      key: key2
```

#### Vault

The Vault section below outlines how the Charmed Temporal Worker can be related
to the [Vault operator charm](https://charmhub.io/vault-k8s) for storing secrets
securely. Once done, the charm can be configured to fetch secrets from Vault and
inject them as environment variables into the workload container. The secrets
can be configured into the charm as follows:

##### **`environment.yaml`**

```yaml
environment:
  vault:
    - path: my-secrets
      key: key1
    - path: my-secrets
      key: key2
```

These secrets can then be added to Vault by running the following charm action:

```bash
juju run temporal-worker-k8s/leader add-vault-secret path="my-secrets" key="key1" value="value1"
```

## Verifying

To verify that the setup is running correctly, run `juju status --watch 2s` and
ensure the pod is active.

To run a basic workflow, you may use a simple client (e.g.
[sdk-python sample](https://github.com/temporalio/sdk-python#quick-start)) and
connect to the same Temporal server. If run on the same namespace and task queue
as the Temporal Worker, it should be executed successfully.

## Enable Proxy

To enable the Temporal worker charm to use an HTTP proxy, the following Juju
model configurations can be set. The charm will read these values and set the
`HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` environment in the workload container
respectively.

```bash
juju model-config juju-http-proxy="<http_proxy>"
juju model-config juju-https-proxy="<https_proxy>"
juju model-config juju-no-proxy="<no_proxy>"
```

A config change may be needed if your charm is already deployed to force the
charm to re-initialize.

## Scaling

To add more replicas you can use the juju scale-application functionality i.e.

```
juju scale-application temporal-worker-k8s <num_of_replicas_required_replicas>
```

## Error Monitoring

The Charmed Temporal Worker has a built-in Sentry interceptor which can be used
to intercept and capture errors from the Temporal SDK. To enable it, run the
following commands:

```bash
juju config temporal-worker-k8s sentry-dsn=<YOUR_SENTRY_DSN>
juju config temporal-worker-k8s sentry-release="1.0.0"
juju config temporal-worker-k8s sentry-environment="staging"
```

## Observability

The Charmed Temporal Worker can be related to the
[Canonical Observability Stack](https://charmhub.io/topics/canonical-observability-stack)
in order to collect logs and telemetry. To deploy cos-lite and expose its
endpoints as offers, follow these steps:

```bash
# Deploy the cos-lite bundle:
juju add-model cos
juju deploy cos-lite --trust
```

```bash
# Expose the cos integration endpoints:
juju offer prometheus:metrics-endpoint
juju offer loki:logging
juju offer grafana:grafana-dashboard

# Relate Temporal to the cos-lite apps:
juju relate temporal-worker-k8s admin/cos.grafana
juju relate temporal-worker-k8s admin/cos.loki
juju relate temporal-worker-k8s admin/cos.prometheus
```

```bash
# Access grafana with username "admin" and password:
juju run grafana/0 -m cos get-admin-password --wait 1m
# Grafana is listening on port 3000 of the app ip address.
# Dashboard can be accessed under "Temporal Worker SDK Metrics", make sure to select the juju model which contains your Charmed Temporal Worker.
```

## Vault

The Charmed Temporal Worker can be related to the
[Vault operator charm](https://charmhub.io/vault-k8s) to securely store
credentials that can be accessed by workflows. This is the recommended way of
storing workflow-related credentials in production environments. To enable this,
run the following commands:

```bash
juju deploy vault-k8s --channel 1.16/edge

# After following Vault doc instructions to unseal Vault
juju relate temporal-worker-k8s vault-k8s
```

Note: The vault charm currently needs to be manually unsealed using the
instructions found [here](https://charmhub.io/vault-k8s/docs/h-getting-started).

For a reference on how to access credentials from Vault through the workflow
code,
[`activity2.py`](./resource_sample_py/resource_sample/activities/activity2.py)
under the `resource_sample` directory shows a sample for writing and reading
secrets in Vault.

**Note**: At the time of writing, the Vault operator charm currently has
compatibility issues with some versions of Juju (e.g. Juju `v3.2.4`). It has
been tested successfully with Juju
[`v3.3.5`](https://github.com/canonical/temporal-worker-k8s-operator/actions/runs/9874524137/job/27269330380).

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer guidance.
