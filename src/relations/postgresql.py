# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Temporal worker postgresql relation."""

import json
import logging

from ops import RelationBrokenEvent

logger = logging.getLogger(__name__)

# Peer application databag key read by the previous revisions of the charm.
LEGACY_DATABASE_CONNECTION_KEY = "database_connection"


class Postgresql:
    """Reader of the postgresql relation."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm owning the relation.
        """
        self.charm = charm

    def connection(self) -> dict | None:
        """Read the database connection info from the database relation.

        Returns:
            The connection info, or None if the relation does not provide a usable connection yet.
        """
        relation = self.charm.model.get_relation("database")
        if relation is None:
            return None

        relation_data = self.charm.database.fetch_relation_data().get(relation.id, {})

        endpoints = relation_data.get("endpoints", "").split(",")
        primary_endpoint = endpoints[0].split(":")
        if len(primary_endpoint) < 2:
            return None

        db_conn = {
            "host": primary_endpoint[0],
            "port": primary_endpoint[1],
            "password": relation_data.get("password"),
            "user": relation_data.get("username"),
            "tls": relation_data.get("tls"),
        }

        if None in (db_conn["user"], db_conn["password"]):
            return None

        return db_conn

    def sync_legacy_peer_state(self, event) -> None:
        """Keep the `database_connection` value of the previous revisions up to date; leader only.

        This unit reads the connection info from the database relation. During a rolling upgrade, the units still
        running a previous revision read it from the peer relation, where it is JSON encoded, and the leader may
        already be upgraded and the only one updating it: the value is never removed or reshaped, and kept up to
        date, in the format of the previous revisions, for as long as the relation provides data.

        Args:
            event: The event being reconciled.
        """
        peer = self.charm.model.get_relation("peer")
        if not self.charm.unit.is_leader() or peer is None:
            return

        if isinstance(event, RelationBrokenEvent) and event.relation.name == "database":
            connection = None
        else:
            connection = self.connection()
            if connection is None:
                return

        encoded = json.dumps(connection)
        if peer.data[self.charm.app].get(LEGACY_DATABASE_CONNECTION_KEY) != encoded:
            peer.data[self.charm.app][LEGACY_DATABASE_CONNECTION_KEY] = encoded
