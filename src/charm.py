#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm definition and helpers."""

import json
import logging
from pathlib import Path

from ops import main
from ops.charm import CharmBase
from ops.model import ActiveStatus, BlockedStatus, Container, WaitingStatus

from log import log_event_handler

logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]
REQUIRED_CHARM_CONFIG = ["host", "namespace", "queue"]
REQUIRED_CANDID_CONFIG = ["candid-url", "candid-username", "candid-public-key", "candid-private-key"]
REQUIRED_OIDC_CONFIG = [
    "oidc-auth-type",
    "oidc-project-id",
    "oidc-private-key-id",
    "oidc-private-key",
    "oidc-client-email",
    "oidc-client-id",
    "oidc-auth-uri",
    "oidc-token-uri",
    "oidc-auth-cert-url",
    "oidc-client-cert-url",
]
SUPPORTED_AUTH_PROVIDERS = ["candid", "google"]


class TemporalWorkerK8SOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)
        self.name = "temporal-worker"

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.temporal_worker_pebble_ready, self._on_temporal_worker_pebble_ready)

    @log_event_handler(logger)
    def _on_temporal_worker_pebble_ready(self, event):
        """Define and start temporal using the Pebble API.

        Args:
            event: The event triggered when the relation changed.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle configuration changes.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring temporal worker")
        self._update(event)

    def _validate(self):
        """Validate that configuration and relations are valid and ready.

        Raises:
            ValueError: in case of invalid configuration.
        """
        log_level = self.model.config["log-level"].lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"config: invalid log level {log_level!r}")

        self._check_required_config(REQUIRED_CHARM_CONFIG)

        if self.config["auth-enabled"]:
            if not self.config["auth-provider"]:
                raise ValueError("Invalid config: auth-provider value missing")

            if not self.config["auth-provider"] in SUPPORTED_AUTH_PROVIDERS:
                raise ValueError("Invalid config: auth-provider not supported")

            if self.config["auth-provider"] == "candid":
                self._check_required_config(REQUIRED_CANDID_CONFIG)

            if self.config["auth-provider"] == "google":
                self._check_required_config(REQUIRED_OIDC_CONFIG)

    def _check_required_config(self, config_list):
        """Check if required config has been set by user.

        Args:
            config_list: list of required config parameters.

        Raises:
            ValueError: if any of the required config is not set.
        """
        for param in config_list:
            if self.config[param].strip() == "":
                raise ValueError(f"Invalid config: {param} value missing")

    def _update(self, event):
        """Update the Temporal worker configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._validate()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            return

        # ensure the container is set up
        _setup_container(container)

        logger.info("Configuring Temporal worker")

        pebble_layer = {
            "summary": "temporal worker layer",
            "services": {
                self.name: {
                    "summary": "temporal worker",
                    "command": f"python worker.py '{json.dumps(dict(self.config))}'",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }

        container.add_layer(self.name, pebble_layer, combine=True)
        container.replan()

        self.unit.status = ActiveStatus()


def _setup_container(container: Container):
    """Copy worker file to the container and install dependencies.

    Args:
        container: Container unit on which to perform action.
    """
    resources_path = Path(__file__).parent / "resources"
    _push_container_file(container, resources_path, "/worker.py", resources_path / "worker.py")
    _push_container_file(
        container,
        resources_path,
        "/temporal_client/__init__.py",
        resources_path / "temporal_client/__init__.py",
    )
    _push_container_file(
        container,
        resources_path,
        "/temporal_client/workflows.py",
        resources_path / "temporal_client/workflows.py",
    )
    _push_container_file(
        container,
        resources_path,
        "/temporal_client/activities.py",
        resources_path / "temporal_client/activities.py",
    )

    # Install worker dependencies
    worker_dependencies_path = resources_path / "worker-dependencies.txt"
    with open(worker_dependencies_path, "r") as dependencies_file:
        dependencies = dependencies_file.read().split("\n")
        logger.info(f"installing worker dependencies {dependencies}...")
        container.exec(["pip", "install", *dependencies]).wait()


def _push_container_file(container: Container, src_path, dest_path, resource):
    """Copy worker file to the container and install dependencies.

    Args:
        container: Container unit on which to perform action.
        src_path: resource path.
        dest_path: destination path on container.
        resource: resource to push to container.
    """
    source_path = src_path / resource
    with open(source_path, "r") as file_source:
        logger.info(f"pushing {resource} source...")
        container.push(dest_path, file_source, make_dirs=True)


if __name__ == "__main__":  # pragma: nocover
    main.main(TemporalWorkerK8SOperatorCharm)
