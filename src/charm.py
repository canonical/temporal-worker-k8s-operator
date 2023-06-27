#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm definition and helpers."""

import json
import logging
from pathlib import Path

from dotenv import dotenv_values
from ops import main
from ops.charm import CharmBase
from ops.model import ActiveStatus, BlockedStatus, Container, ModelError, WaitingStatus

from actions.activities import ActivitiesActions
from actions.dependencies import DependenciesActions
from actions.workflows import WorkflowsActions
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

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.temporal_worker_pebble_ready, self._on_temporal_worker_pebble_ready)

        self.workflows_actions = WorkflowsActions(self)
        self.activities_actions = ActivitiesActions(self)
        self.dependencies_actions = DependenciesActions(self)

    @log_event_handler(logger)
    def _on_temporal_worker_pebble_ready(self, event):
        """Define and start temporal using the Pebble API.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self._state.is_ready():
            event.defer()
            return

        if self.unit.is_leader():
            if self._state.supported_workflows is None:
                self._state.supported_workflows = []
            if self._state.supported_activities is None:
                self._state.supported_activities = []
            if self._state.supported_dependencies is None:
                self._state.supported_dependencies = []

        self._update(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle configuration changes.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring temporal worker")

        self._process_env_file(event)
        try:
            self._process_wheel_file(event)
            self._update(event)
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

    def _validate(self):  # noqa: C901
        """Validate that configuration and relations are valid and ready.

        Raises:
            ValueError: in case of invalid configuration.
        """
        log_level = self.model.config["log-level"].lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"config: invalid log level {log_level!r}")

        if not self._state.is_ready():
            raise ValueError("peer relation not ready")

        self._check_required_config(REQUIRED_CHARM_CONFIG)

        if self._state.supported_workflows is None or len(self._state.supported_workflows) == 0:
            raise ValueError("Invalid state: must have at least one supported workflow")

        if self._state.supported_activities is None or len(self._state.supported_activities) == 0:
            raise ValueError("Invalid state: must have at least one supported activity")

        if self._state.module_name is None:
            raise ValueError("Invalid state: error extracting folder name from wheel file")

        if self.config["auth-enabled"]:
            if not self.config["auth-provider"]:
                raise ValueError("Invalid config: auth-provider value missing")

            if not self.config["auth-provider"] in SUPPORTED_AUTH_PROVIDERS:
                raise ValueError("Invalid config: auth-provider not supported")

            if self.config["auth-provider"] == "candid":
                self._check_required_config(REQUIRED_CANDID_CONFIG)

            if self.config["auth-provider"] == "google":
                self._check_required_config(REQUIRED_OIDC_CONFIG)

    def _process_env_file(self, event):
        """Process env file attached by user.

        This method extracts the env file provided by the user and stores the data in the
        charm's data bucket.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._state.env = None
            resource_path = self.model.resources.fetch("env-file")
            env = dotenv_values(resource_path)
            self._state.env = env
        except ModelError as err:  # noqa: F841
            logger.error(err)

    def _process_wheel_file(self, event):
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

        try:
            resource_path = self.model.resources.fetch("workflows-file")

            container = self.unit.get_container(self.name)
            if not container.can_connect():
                event.defer()
                self.unit.status = WaitingStatus("waiting for pebble api")
                return

            container.exec(["rm", "-rf", "/user_provided"]).wait_output()

            with open(resource_path, "rb") as file:
                wheel_data = file.read()

                # Push wheel file to the container and extract it.
                container.push("/user_provided/wheel_file.whl", wheel_data, make_dirs=True)
                container.exec(["apt-get", "update"]).wait_output()
                container.exec(["apt-get", "install", "unzip"]).wait_output()
                container.exec(["unzip", "/user_provided/wheel_file.whl", "-d", "/user_provided"]).wait_output()

                # Find the name of the module provided by the user and set it in state.
                command = "find /user_provided -mindepth 1 -maxdepth 1 -type d ! -name *.dist-info ! -name *.whl"
                out, error = container.exec(command.split(" ")).wait_output()

                if error is not None and error.strip() != "":
                    logger.error(f"failed to extract module name from wheel file: {error}")
                    raise ValueError("Invalid state: failed to extract module name from wheel file")

                module_name = out.split("\n")
                if self.unit.is_leader():
                    self._state.module_name = module_name[0].split("/")[-1]

        except ModelError as err:  # noqa: F841
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
            self.unit.status = WaitingStatus("waiting for pebble api")
            return

        # ensure the container is set up
        _setup_container(container)

        logger.info("Configuring Temporal worker")

        module_name = self._state.module_name
        sw = self._state.supported_workflows
        sa = self._state.supported_activities
        command = f"python worker.py '{json.dumps(dict(self.config))}' '{','.join(sw)}' '{','.join(sa)}' {module_name}"

        pebble_layer = {
            "summary": "temporal worker layer",
            "services": {
                self.name: {
                    "summary": "temporal worker",
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "environment": self._state.env,
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
        container, resources_path, "/worker-dependencies.txt", resources_path / "worker-dependencies.txt"
    )

    # Install worker dependencies
    worker_dependencies_path = "/worker-dependencies.txt"
    logger.info("installing worker dependencies...")
    container.exec(["pip", "install", "-r", str(worker_dependencies_path)]).wait_output()


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
