# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the host info relation."""

import logging

from ops import RelationChangedEvent, RelationJoinedEvent, framework
from ops.charm import CharmBase

from log import log_event_handler

logger = logging.getLogger(__name__)


class HostInfoProvider(framework.Object):
    def __init__(self, charm: CharmBase, port: int):
        super().__init__(charm, "host_info_provider")
        self.charm = charm
        self.port = port
        charm.framework.observe(charm.on.host_info_relation_joined, self._on_host_info_relation_changed)
        charm.framework.observe(charm.on.host_info_relation_changed, self._on_host_info_relation_changed)
        charm.framework.observe(charm.on.leader_elected, self._on_host_info_relation_changed)

    @log_event_handler(logger)
    def _on_host_info_relation_changed(self, event: RelationChangedEvent | RelationJoinedEvent):
        if self.charm.unit.is_leader():
            host = self.charm.config["external-hostname"] or self.model.get_binding("host-info").network.bind_address
            event.relation.data[self.charm.app] = {"host": host, "port": self.port}


class HostInfoRelationReadyEvent(framework.EventBase):
    """Event emitted when host info relation is ready."""

    def __init__(
        self,
        handle: framework.Handle,
        host: str,
        port: int,
    ):
        super().__init__(handle)
        self.host = host
        self.port = port

    def snapshot(self) -> dict[str, str | int]:
        """Return a snapshot of the event."""
        return {"host": self.host, "port": self.port}

    def restore(self, snapshot: dict[str, str | int]) -> None:
        """Restore the event from a snapshot."""
        self.host = snapshot["host"]  # type: ignore[assignment]
        self.port = snapshot["port"]  # type: ignore[assignment]


class HostInfoRequirerCharmEvents(framework.CharmEvents):
    """List of events that the TLS Certificates requirer charm can leverage."""

    host_info_available = framework.EventSource(HostInfoRelationReadyEvent)


class HostInfoRequirer(framework.Object):
    def __init__(self, charm: CharmBase):
        super().__init__(charm, "host_info_requirer")
        self.charm = charm
        self.on = HostInfoRequirerCharmEvents()
        self.host: str | None = None
        self.port: int | None = None
        charm.framework.observe(charm.on.host_info_relation_joined, self._on_host_info_relation_changed)
        charm.framework.observe(charm.on.host_info_relation_changed, self._on_host_info_relation_changed)

    @log_event_handler(logger)
    def _on_host_info_relation_changed(self, event: RelationChangedEvent):
        if relation := self.charm.model.get_relation("host-info"):
            if data := relation.data.get(relation.app):
                self.host = data.get("host")
                self.port = int(data.get("port"))
                self.on.host_info_available.emit(host=self.host, port=self.port)
