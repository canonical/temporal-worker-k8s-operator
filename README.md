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

## Verifying

To verify that the setup is running correctly, run `juju status --watch 1s` and
ensure the pod is active.

To run a basic workflow, you may use a simple client (e.g.
[sdk-python sample](https://github.com/temporalio/sdk-python#quick-start)) and
connect to the same Temporal server. If run on the same namespace and task queue
as the Temporal worker, it should be executed successfully.

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer guidance.
