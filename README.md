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

### Defining supported workflows and activities

Once the wheel file is processed by the worker to extract all the workflows and
activities, a list of supported workflows and activities must be defined by the
user before the charm can be started. This can be done as follows:

```bash
juju run temporal-worker-k8s/0 add-workflows workflows="GreetingWorkflow"
juju run temporal-worker-k8s/0 add-activities activities="compose_greeting"
```

Once done, the charm should enter an active state, indicating that the worker is
running successfully. To verify this, you can check the logs of the kubernetes
pod to ensure there are no errors with the workload container:

```bash
kubectl -n <juju_model_name> logs temporal-worker-k8s-0 -c temporal-worker -f
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
