# Sample ROCK project

This is a sample
[ROCK image](https://documentation.ubuntu.com/rockcraft/en/stable/explanation/rocks/#rocks-explanation)
that can be used to build Python-based Temporal workflows.

To work with the charm, the root directory must include a
`scripts/start-worker.sh` file, with a command that would start your
asynchronous Temporal worker.

To test the worker locally, export the relevant environment variables found in
[`rockcraft.yaml`](./rockcraft.yaml) and start the worker by running
`poetry run python resource_sample/worker.py`.

To build the ROCK image, you must enable a local registry as outlined in
[`CONTRIBUTING.md`](../CONTRIBUTING.md). You can then run `make build_rock` to
build the ROCK and push it to a local registry.

To start the image, you can run the following command:

```bash
docker run -d --name temporal-worker -p 8088:8088 localhost:32000/temporal-worker-rock start temporal-worker
```
