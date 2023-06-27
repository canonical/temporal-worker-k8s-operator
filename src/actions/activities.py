# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Temporal worker activities actions."""

# pylint: disable=W0212,R0801

import logging

from ops import framework

from log import log_event_handler

logger = logging.getLogger(__name__)


class ActivitiesActions(framework.Object):
    """Client for Temporal worker activities actions."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "activities-actions")
        self.charm = charm
        charm.framework.observe(charm.on.add_activities_action, self._on_add_activities_action)
        charm.framework.observe(charm.on.remove_activities_action, self._on_remove_activities_action)
        charm.framework.observe(charm.on.list_activities_action, self._on_list_activities_action)

    @log_event_handler(logger)
    def _on_add_activities_action(self, event):
        """Add to the list of activities supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        if not self.charm.unit.is_leader():
            event.fail("action cannot be performed on non-leader unit")
            return

        sw = self.charm._state.supported_activities
        for workflow in event.params["activities"].split(","):
            if workflow not in sw:
                sw.append(workflow)
        self.charm._state.supported_activities = sw

        event.set_results(
            {"result": "command succeeded", "supported-activities": self.charm._state.supported_activities}
        )
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_remove_activities_action(self, event):
        """Remove from the list of activities supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        if not self.charm.unit.is_leader():
            event.fail("action cannot be performed on non-leader unit")
            return

        sw = [
            item for item in self.charm._state.supported_activities if item not in event.params["activities"].split(",")
        ]
        self.charm._state.supported_activities = sw
        event.set_results(
            {"result": "command succeeded", "supported-activities": self.charm._state.supported_activities}
        )
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_list_activities_action(self, event):
        """Return list of activities supported by worker.

        Args:
            event: The event triggered when the action is triggered.
        """
        if not self.charm._state.is_ready():
            event.defer()
            return

        event.set_results(
            {"result": "command succeeded", "supported-activities": self.charm._state.supported_activities}
        )
