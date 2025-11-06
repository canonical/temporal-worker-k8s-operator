# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Vault relation."""

import logging

from ops import RelationChangedEvent, RelationJoinedEvent, framework
from ops.charm import CharmBase

from log import log_event_handler

logger = logging.getLogger(__name__)


class WorkerConsumerProvider(framework.Object):
    def __init__(self, charm: CharmBase):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "worker_consumer_provider")
        self.charm = charm

        charm.framework.observe(charm.on.worker_consumer_relation_joined, self._on_worker_consumer_changed)
        charm.framework.observe(charm.on.worker_consumer_relation_changed, self._on_worker_consumer_changed)
        charm.framework.observe(charm.on.config_changed, self._on_worker_consumer_changed)

    @log_event_handler(logger)
    def _on_worker_consumer_changed(self, event: RelationChangedEvent | RelationJoinedEvent):
        if self.charm.unit.is_leader():
            event.relation.data[self.charm.app] = {
                "namespace": self.charm.config["namespace"],
                "queue": self.charm.config["queue"],
            }
            # Config could have changed, so update all relations
            for relation in self.charm.model.relations.get("worker-consumer", ()):
                relation.data[self.charm.app]["namespace"] = self.charm.config["namespace"]
                relation.data[self.charm.app]["queue"] = self.charm.config["queue"]


class WorkerConsumerRelationReadyEvent(framework.EventBase):
    """Event emitted when host info relation is ready."""

    def __init__(
        self,
        handle: framework.Handle,
        namespace: str,
        queue: str,
    ):
        super().__init__(handle)
        self.namespace = namespace
        self.queue = queue

    def snapshot(self) -> dict[str, str]:
        """Return a snapshot of the event."""
        return {"namespace": self.namespace, "queue": self.queue}

    def restore(self, snapshot: dict[str, str]) -> None:
        """Restore the event from a snapshot."""
        self.namespace = snapshot["namespace"]
        self.queue = snapshot["queue"]


class WorkerConsumerRequirerCharmEvents(framework.CharmEvents):
    """List of events that the TLS Certificates requirer charm can leverage."""

    worker_consumer_available = framework.EventSource(WorkerConsumerRelationReadyEvent)


class WorkerConsumerRequirer(framework.Object):
    def __init__(self, charm: CharmBase):
        super().__init__(charm, "worker_consumer_requirer")
        self.charm = charm
        self.on = WorkerConsumerRequirerCharmEvents()
        self.namespace: str | None = None
        self.queue: str | None = None
        charm.framework.observe(charm.on.worker_consumer_relation_joined, self._on_worker_consumer_relation_changed)
        charm.framework.observe(charm.on.worker_consumer_relation_changed, self._on_worker_consumer_relation_changed)

    @log_event_handler(logger)
    def _on_worker_consumer_relation_changed(self, event: RelationChangedEvent):
        if relation := self.charm.model.get_relation("worker-consumer"):
            if data := relation.data.get(relation.app):
                self.namespace = data.get("namespace")
                self.queue = data.get("queue")
                self.on.worker_consumer_available.emit(namespace=self.namespace, queue=self.queue)
