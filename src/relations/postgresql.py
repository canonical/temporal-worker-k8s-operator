# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Temporal worker postgresql relation."""

import logging

from ops import framework
from ops.model import WaitingStatus

from literals import DB_NAME
from log import log_event_handler

logger = logging.getLogger(__name__)


class Postgresql(framework.Object):
    """Client for postgresql relations."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "database")
        self.charm = charm

        charm.framework.observe(charm.database.on.database_created, self._on_database_changed)
        charm.framework.observe(charm.database.on.endpoints_changed, self._on_database_changed)
        charm.framework.observe(charm.on.database_relation_broken, self._on_database_relation_broken)

    @log_event_handler(logger)
    def _on_database_changed(self, event) -> None:
        """Handle database creation/change events.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        self.charm.unit.status = WaitingStatus(f"handling {event.relation.name} change")

        self.update_db_relation_data_in_state(event)
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_database_relation_broken(self, event) -> None:
        """Handle broken relations with the database.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm._state.is_ready():
            event.defer()
            return

        self.charm._state.database_connection = None
        self.charm._update(event)

    # flake8: noqa: C901
    def update_db_relation_data_in_state(self, event) -> bool:
        """Update database data from relation into peer relation databag.

        Args:
            event: The event triggering the DB update.

        Returns:
            True if the charm should update its pebble layer, False otherwise.
        """
        if not self.charm.unit.is_leader():
            return False

        if not self.charm._state.is_ready():
            logger.info("charm peer state not ready, deferring db update event")
            event.defer()
            return False

        if self.charm.model.get_relation("database") is None:
            return False

        relation_id = self.charm.database.relations[0].id
        relation_data = self.charm.database.fetch_relation_data()[relation_id]

        endpoints = relation_data.get("endpoints", "").split(",")
        if len(endpoints) < 1:
            return False

        primary_endpoint = endpoints[0].split(":")
        if len(primary_endpoint) < 2:
            return False

        db_conn = {
            "dbname": DB_NAME,
            "host": primary_endpoint[0],
            "port": primary_endpoint[1],
            "password": relation_data.get("password"),
            "user": relation_data.get("username"),
            "tls": relation_data.get("tls"),
        }

        if None in (db_conn["user"], db_conn["password"]):
            return False

        should_update = False
        fields_to_check = ["host", "user", "password", "tls"]
        database_connection = self.charm._state.database_connection or {}
        if any(database_connection.get(field, "") != db_conn[field] for field in fields_to_check):
            should_update = True

        self.charm._state.database_connection = db_conn

        return should_update
