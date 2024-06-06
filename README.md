[![Charmhub Badge](https://charmhub.io/temporal-worker-k8s/badge.svg)](https://charmhub.io/temporal-worker-k8s)
[![Release Edge](https://github.com/canonical/temporal-worker-k8s-operator/actions/workflows/test_and_publish_charm.yaml/badge.svg)](https://github.com/canonical/temporal-worker-k8s-operator/actions/workflows/test_and_publish_charm.yaml)

# Temporal Worker K8s Operator

This is the Kubernetes Python Operator for the Temporal worker.

## Description

Temporal is a developer-first, open source platform that ensures the successful
execution of services and applications (using workflows).

Use Workflow as Code (TM) to build and operate resilient applications. Leverage
developer friendly primitives and avoid fighting your infrastructure

This operator provides a Temporal worker, and consists of Python scripts which
connect to a deployed Temporal server.

## Usage

### Deploying

The Temporal worker operator can be deployed and connected to a deployed
Temporal server using the Juju command line as follows:

```bash
juju deploy temporal-worker-k8s
juju config temporal-worker-k8s --file=path/to/config.yaml
```

#### **`config.yaml`**

```yaml
temporal-worker-k8s:
  host: "localhost:7233" # Replace with Temporal server hostname
  queue: "test-queue"
  namespace: "test"
  workflows-file-name: "python_samples-1.1.0-py3-none-any.whl"
  # To support all defined workflows and activities, use the 'all' keyword
  supported-workflows: "all"
  supported-activities: "all"
```

### Attaching "workflows-file" resource

The Temporal worker operator expects a "workflows-file" resource to be attached
after deployment, which contains a set of defined Temporal workflows and
activities as defined in the [resource_sample](./resource_sample/) directory.
The structure of the built wheel file must follow the same structure:

```
- workflows/
    - workflow-a.py
    - workflow-b.py
- activities/
    - activity-a.py
    - activity-b.py
- some_other_directory/
- some_helper_file.py
```

The sample wheel file can be built by running `poetry build -f wheel` in the
[resource_sample](./resource_sample/) directory.

Once ready, the resource can be attached as follows:

```bash
juju attach-resource temporal-worker-k8s workflows-file=./resource_sample/dist/python_samples-1.1.0-py3-none-any.whl
```

Once done, the charm should enter an active state, indicating that the worker is
running successfully. To verify this, you can check the logs of the kubernetes
pod to ensure there are no errors with the workload container:

```bash
kubectl -n <juju_model_name> logs temporal-worker-k8s-0 -c temporal-worker -f
```

Note: Files defined under the "workflows" directory must only contain classes
decorated using the `@workflow.defn` decorator. Files defined under the
"activities" directory must only contain methods decorated using the
`@activity.defn` decorator. Any additional methods or classes needed should be
defined in other files.

## Verifying

To verify that the setup is running correctly, run `juju status --watch 1s` and
ensure the pod is active.

To run a basic workflow, you may use a simple client (e.g.
[sdk-python sample](https://github.com/temporalio/sdk-python#quick-start)) and
connect to the same Temporal server. If run on the same namespace and task queue
as the Temporal worker, it should be executed successfully.

## Scaling

To add more replicas you can use the juju scale-application functionality i.e.

```
juju scale-application temporal-worker-k8s <num_of_replicas_required_replicas>
```

## Error Monitoring

The Temporal worker operator has a built-in Sentry interceptor which can be used
to intercept and capture errors from the Temporal SDK. To enable it, run the
following commands:

```bash
juju config temporal-worker-k8s sentry-dsn=<YOUR_SENTRY_DSN>
juju config temporal-worker-k8s sentry-release="1.0.0"
juju config temporal-worker-k8s sentry-environment="staging"
```

## Observability

The Temporal worker operator charm can be related to the
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
# Dashboard can be accessed under "Temporal Worker SDK Metrics", make sure to select the juju model which contains your Temporal worker operator charm.
```

## Vault

The Temporal worker operator charm can be related to the
[Vault operator charm](https://charmhub.io/vault-k8s) to securely store
credentials that can be accessed by workflows. This is the recommended way of
storing workflow-related credentials in production environments. To enable this,
run the following commands:

```bash
juju deploy vault-k8s --channel edge

# After following Vault doc instructions to unseal Vault
juju relate temporal-worker-k8s vault-k8s
```

For a reference on how to access credentials from Vault through the workflow
code,
[`activity2.py`](./resource_sample/resource_sample/activities/activity2.py)
under the `resource_sample` directory shows a sample for writing and reading
secrets in Vault.

**Note**: At the time of writing, the Vault operator charm currently has
compatibility issues with some versions of Juju (e.g. Juju `v3.2.4`). It has
been tested successfully with Juju `v3.1.8`.

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer guidance.
