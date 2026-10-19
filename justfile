# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

set export

charm := "./temporal-worker-k8s_ubuntu@24.04-amd64.charm"
rock := "./resource_sample_py/temporal-worker_1.0_amd64.rock"
image := "localhost:32000/temporal-worker:1.0"

[private]
default:
	just --list

# Format the code
format:
	uv tool run --with tox-uv tox -e fmt

# Run linters
lint:
	uv tool run --with tox-uv tox -e lint

# Run unit tests
unit:
	uv tool run --with tox-uv tox -e unit

# Pack the charm and the temporal-worker rock, and push the rock to the local registry
pack:
	charmcraft pack
	cd resource_sample_py && rockcraft pack
	rockcraft.skopeo --insecure-policy copy --dest-tls-verify=false oci-archive:{{rock}} docker://{{image}}

# Run integration tests
integration *args: pack
	uv tool run --with tox-uv tox -e integration -- --charm-file={{charm}} --temporal-worker-image={{image}} {{args}}

# Print system state to help debug a failed run
get-system-state:
	#!/usr/bin/bash
	df -h
	echo "---"
	juju status --relations --storage --color || true
	echo "---"
	sudo k8s status || true
