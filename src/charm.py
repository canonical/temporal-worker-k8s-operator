#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm definition and helpers."""

import json
import logging
import re
from pathlib import Path

from dotenv import dotenv_values
from ops import main
from ops.charm import CharmBase
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    Container,
    MaintenanceStatus,
    ModelError,
    WaitingStatus,
)

from literals import (
    REQUIRED_CANDID_CONFIG,
    REQUIRED_CHARM_CONFIG,
    REQUIRED_OIDC_CONFIG,
    SUPPORTED_AUTH_PROVIDERS,
    VALID_LOG_LEVELS,
)
from log import log_event_handler
from state import State

logger = logging.getLogger(__name__)


class TemporalWorkerK8SOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)
        self._state = State(self.app, lambda: self.model.get_relation("peer"))
        self.name = "temporal-worker"

        self.framework.observe(self.on.peer_relation_changed, self._on_peer_relation_changed)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.temporal_worker_pebble_ready, self._on_temporal_worker_pebble_ready)
        self.framework.observe(self.on.restart_action, self._on_restart)

    @log_event_handler(logger)
    def _on_temporal_worker_pebble_ready(self, event):
        """Define and start temporal using the Pebble API.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self._state.is_ready():
            event.defer()
            return

        self._update(event)

    @log_event_handler(logger)
    def _on_restart(self, event):
        """Restart Temporal worker action handler.

        Args:
            event:The event triggered by the restart action
        """
        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            return

        self.unit.status = MaintenanceStatus("restarting worker")
        container.restart(self.name)
        self.unit.status = ActiveStatus(
            f"worker listening to namespace {self.config['namespace']!r} on queue {self.config['queue']!r}"
        )

        event.set_results({"result": "worker successfully restarted"})

    @log_event_handler(logger)
    def _on_peer_relation_changed(self, event):
        """Handle peer relation changed event.

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

    def _process_env_file(self, event):
        """Process env file attached by user.

        This method extracts the env file provided by the user and stores the data in the
        charm's data bucket.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self._state.is_ready():
            event.defer()
            return

        if self.unit.is_leader():
            self._state.env = None

        try:
            resource_path = self.model.resources.fetch("env-file")
            env = dotenv_values(resource_path)
            self._state.env = env
        except ModelError as err:
            logger.error(err)

    def _process_wheel_file(self, event):  # noqa: C901
        """Process wheel file attached by user.

        This method extracts the wheel file provided by the user and places the contents
        into the workload container, which can then be read by the Temporal worker.

        Args:
            event: The event triggered when the relation changed.

        Raises:
            ValueError: if file is not found.
        """
        if not self._state.is_ready():
            event.defer()
            return

        if self.unit.is_leader():
            self._state.module_name = None

        if self.config["workflows-file-name"].strip() == "":
            raise ValueError("Invalid config: wheel-file-name missing")

        if not _validate_wheel_name(self.config["workflows-file-name"]):
            raise ValueError("Invalid config: invalid wheel-file-name")

        try:
            resource_path = self.model.resources.fetch("workflows-file")
            filename = Path(resource_path).name

            container = self.unit.get_container(self.name)
            if not container.can_connect():
                event.defer()
                self.unit.status = WaitingStatus("waiting for pebble api")
                return

            container.exec(["rm", "-rf", "/user_provided"]).wait_output()

            with open(resource_path, "rb") as file:
                wheel_data = file.read()

                wheel_file = f"/user_provided/{filename}"
                original_wheel_file = f"/user_provided/{self.config['workflows-file-name']}"

                # Push wheel file to the container and extract it.
                container.push(wheel_file, wheel_data, make_dirs=True)

                # Rename wheel file to its original name and install it
                container.exec(["mv", wheel_file, original_wheel_file]).wait()

                _, error = container.exec(["pip", "install", original_wheel_file]).wait_output()
                if error is not None and error.strip() != "" and not error.strip().startswith("WARNING"):
                    logger.error(f"failed to install wheel file: {error}")
                    raise ValueError("Invalid state: failed to install wheel file")

                # Unpack wheel file
                container.exec(["pip", "install", "wheel"]).wait()
                _, error = container.exec(
                    ["wheel", "unpack", original_wheel_file, "-d", "/user_provided"]
                ).wait_output()
                if error is not None and error.strip() != "" and not error.strip().startswith("WARNING"):
                    logger.error(f"failed to unpack wheel file: {error}")
                    raise ValueError("Invalid state: failed to unpack wheel file")

                wheel_arr = self.config["workflows-file-name"].split("-")
                unpacked_file_name = f"/user_provided/{'-'.join(wheel_arr[0:2])}"

                # Find the name of the module provided by the user and set it in state.
                command = f"find {unpacked_file_name} -mindepth 1 -maxdepth 1 -type d ! -name *.dist-info ! -name *.whl"
                out, error = container.exec(command.split(" ")).wait_output()

                if error is not None and error.strip() != "":
                    logger.error(f"failed to extract module name from wheel file: {error}")
                    raise ValueError("Invalid state: failed to extract module name from wheel file")

                directories = out.split("\n")
                module_name = Path(directories[0]).name

                if self.unit.is_leader():
                    self._state.module_name = module_name

                command = f"find {unpacked_file_name}/{module_name} -mindepth 1 -maxdepth 1 -type d"
                out, _ = container.exec(command.split(" ")).wait_output()
                provided_directories = out.split("\n")
                required_directories = ["workflows", "activities"]
                for d in required_directories:
                    if f"{unpacked_file_name}/{module_name}/{d}" not in provided_directories:
                        raise ValueError(f"Invalid state: {d} directory not found in attached resource")

        except ModelError as err:
            logger.error(err)
            raise ValueError("Invalid state: workflows-file resource not found") from err

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

    def _validate(self, event):  # noqa: C901
        """Validate that configuration and relations are valid and ready.

        Args:
            event: The event triggered when the relation changed.

        Raises:
            ValueError: in case of invalid configuration.
        """
        log_level = self.model.config["log-level"].lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"config: invalid log level {log_level!r}")

        if not self._state.is_ready():
            raise ValueError("peer relation not ready")

        self._process_wheel_file(event)
        self._process_env_file(event)

        self._check_required_config(REQUIRED_CHARM_CONFIG)

        if self._state.module_name is None:
            raise ValueError("Invalid state: error extracting folder name from wheel file")

        if self.config["auth-enabled"]:
            if not self.config["auth-provider"]:
                raise ValueError("Invalid config: auth-provider value missing")

            if not self.config["auth-provider"] in SUPPORTED_AUTH_PROVIDERS:
                raise ValueError("Invalid config: auth-provider not supported")

            if self.config["auth-provider"] == "candid":
                self._check_required_config(REQUIRED_CANDID_CONFIG)
            elif self.config["auth-provider"] == "google":
                self._check_required_config(REQUIRED_OIDC_CONFIG)

    def _update(self, event):
        """Update the Temporal worker configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._validate(event)
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("waiting for pebble api")
            return

        # ensure the container is set up
        _setup_container(container)

        logger.info("Configuring Temporal worker")

        module_name = self._state.module_name
        command = f"python worker.py '{json.dumps(dict(self.config))}' {module_name}"

        pebble_layer = {
            "summary": "temporal worker layer",
            "services": {
                self.name: {
                    "summary": "temporal worker",
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "environment": self._state.env or {},
                }
            },
        }

        container.add_layer(self.name, pebble_layer, combine=True)
        container.replan()

        self.unit.status = ActiveStatus(
            f"worker listening to namespace {self.config['namespace']!r} on queue {self.config['queue']!r}"
        )


def _setup_container(container: Container):
    """Copy worker file to the container and install dependencies.

    Args:
        container: Container unit on which to perform action.
    """
    resources_path = Path(__file__).parent / "resources"
    _push_container_file(container, resources_path, "/worker.py", resources_path / "worker.py")
    _push_container_file(
        container, resources_path, "/worker-dependencies.txt", resources_path / "worker-dependencies.txt"
    )

    # Install worker dependencies
    worker_dependencies_path = "/worker-dependencies.txt"
    logger.info("installing worker dependencies...")
    container.exec(["pip", "install", "-r", str(worker_dependencies_path)]).wait_output()


def _validate_wheel_name(filename):
    """Validate wheel file name.

    Args:
        filename: Name of the wheel file.

    Returns:
        True if the file name is valid, False otherwise.
    """
    # Define an allowed list of allowed characters and patterns
    allowed_pattern = r"^[a-zA-Z0-9-._]+-[a-zA-Z0-9_.]+-([a-zA-Z0-9_.]+|any|py2.py3)-(none|linux|macosx|win)-(any|any|intel|amd64)\.whl$"
    return bool(re.match(allowed_pattern, filename))


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
