# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Temporal worker dependencies actions."""

# pylint: disable=W0212,R0801

import logging
import re

from ops import framework
from ops.model import WaitingStatus

from log import log_event_handler

logger = logging.getLogger(__name__)


class DependenciesActions(framework.Object):
    """Client for Temporal worker dependencies actions."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "dependencies-actions")
        self.charm = charm
        charm.framework.observe(charm.on.add_dependencies_action, self._on_add_dependencies_action)
        charm.framework.observe(charm.on.remove_dependencies_action, self._on_remove_dependencies_action)
        charm.framework.observe(charm.on.list_dependencies_action, self._on_list_dependencies_action)

    @log_event_handler(logger)
    def _on_add_dependencies_action(self, event):
        """Add to the list of dependencies supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        if not self.charm.unit.is_leader():
            event.fail("action cannot be performed on non-leader unit")
            return

        container = self.charm.unit.get_container(self.charm.name)
        if not container.can_connect():
            event.defer()
            self.charm.unit.status = WaitingStatus("waiting for pebble api")
            return

        sd = self.charm._state.supported_dependencies
        rejected_dependencies = []

        for dependency in event.params["dependencies"].split(","):
            if dependency not in sd:
                if not _validate_dependency(dependency):
                    rejected_dependencies.append(dependency)
                else:
                    _, error = _run_container_pip_action(container, "install", dependency)
                    if error is not None and error.strip() != "" and not error.strip().startswith("WARNING"):
                        logger.error(f"Error installing {dependency}: {error}")
                        rejected_dependencies.append(dependency)
                    else:
                        # Remove dependency from list if previous version exists
                        package = dependency.split("=")[0].split(">")[0]
                        sd = [item for item in sd if not item.startswith(package)]

                        sd.append(dependency)

        self.charm._state.supported_dependencies = sd

        event.set_results(
            {
                "result": "command succeeded",
                "installed-dependencies": self.charm._state.supported_dependencies,
                "rejected-dependencies": rejected_dependencies,
            }
        )
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_remove_dependencies_action(self, event):
        """Remove from the list of dependencies supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        if not self.charm.unit.is_leader():
            event.fail("action cannot be performed on non-leader unit")
            return

        container = self.charm.unit.get_container(self.charm.name)
        if not container.can_connect():
            event.defer()
            self.charm.unit.status = WaitingStatus("waiting for pebble api")
            return

        sd = self.charm._state.supported_dependencies
        rejected_dependencies = []
        removed_dependencies = []

        for dependency in event.params["dependencies"].split(","):
            if dependency not in sd:
                rejected_dependencies.append(dependency)
            else:
                if not _validate_dependency(dependency):
                    rejected_dependencies.append(dependency)
                else:
                    _, error = _run_container_pip_action(container, "uninstall", dependency)
                    if error is not None and error.strip() != "" and not error.strip().startswith("WARNING"):
                        logger.error(f"Error uninstalling {dependency}: {error}")
                        rejected_dependencies.append(dependency)
                    else:
                        removed_dependencies.append(dependency)
                        sd.remove(dependency)

        self.charm._state.supported_dependencies = sd
        event.set_results(
            {
                "result": "command succeeded",
                "installed-dependencies": self.charm._state.supported_dependencies,
                "removed-dependencies": removed_dependencies,
                "rejected-dependencies": rejected_dependencies,
            }
        )
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_list_dependencies_action(self, event):
        """Return list of dependencies supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        event.set_results(
            {"result": "command succeeded", "installed-dependencies": self.charm._state.supported_dependencies}
        )


def _run_container_pip_action(container, action, dependency):
    """Run pip action on workload container with a given dependency.

    Args:
        container: Workload container to run the action on.
        action: pip action to run.
        dependency: Dependency on which to run the action.

    Returns:
        Output and optional error from running action on workload container.
    """
    out, error = container.exec(["pip", action, dependency]).wait_output()
    return out, error


def _validate_dependency(dependency):
    """Validate pip dependency.

    Args:
        dependency: Pip packages to be validated.

    Returns:
        True if the dependency is valid, False otherwise.
    """
    # Define a whitelist of allowed characters and patterns
    allowed_pattern = r"^[a-zA-Z0-9_.=<>-]+$"
    return bool(re.search(allowed_pattern, dependency))
