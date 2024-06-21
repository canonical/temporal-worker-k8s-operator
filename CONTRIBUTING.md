# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://juju.is/docs/sdk/dev-setup).

You can create an environment for development with `tox`:

```shell
tox devenv -e integration
source venv/bin/activate
```

## Testing

This project uses `tox` for managing test environments. There are some
pre-configured environments that can be used for linting and formatting code
when you're preparing contributions to the charm:

```shell
tox run -e fmt        # update your code according to linting rules
tox run -e lint          # code style
tox run -e unit          # unit tests
tox run -e integration   # integration tests
tox                      # runs 'format', 'lint', and 'unit' environments
```

### Deploy

This charm is used to deploy Temporal server in a k8s cluster. For a local
deployment, follow the following steps:

    # Install Microk8s from snap:
    sudo snap install microk8s --classic --channel=1.24

    # Install charmcraft from snap:
    sudo snap install charmcraft --classic

    # Install Rockcraft from snap:
    sudo snap install rockcraft --classic

    # Add the 'ubuntu' user to the Microk8s group:
    sudo usermod -a -G microk8s ubuntu

    # Give the 'ubuntu' user permissions to read the ~/.kube directory:
    sudo chown -f -R ubuntu ~/.kube

    # Create the 'microk8s' group:
    newgrp microk8s

    # Enable the necessary Microk8s addons:
    microk8s enable hostpath-storage dns registry

    # Install the Juju CLI client, juju:
    sudo snap install juju --classic

    # Install a "juju" controller into your "microk8s" cloud:
    juju bootstrap microk8s temporal-controller

    # Create a 'model' on this controller:
    juju add-model temporal

    # Enable DEBUG logging:
    juju model-config logging-config="<root>=INFO;unit=DEBUG"

    # Pack the charm:
    charmcraft pack

    # Build ROCK file and push it to local registry:
    cd resource_sample_py && make build_rock

    # Deploy the charm:
    juju deploy ./temporal-worker-k8s_ubuntu-22.04-amd64.charm --resource temporal-worker-image=localhost:32000/temporal-worker-rock
    juju config temporal-worker-k8s --file=path/to/config.yaml

    # Check progress:
    juju status --relations --watch 2s
    juju debug-log

    # Clean-up before retrying:
    juju remove-application temporal-worker-k8s --force
