# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Temporal worker postgresql relation."""

import logging

from ops import framework

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

    # flake8: noqa: C901
    def update_db_relation_data_in_state(self) -> bool:
        """Update database data from relation into peer relation databag.

        Returns:
            True if the charm should update its pebble layer, False otherwise.
        """
        if not self.charm.unit.is_leader():
            return False

        if not self.charm._state.is_ready():
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
