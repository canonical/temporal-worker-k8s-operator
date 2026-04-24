# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm library for the temporal-worker-info Juju relation.

`temporal-worker-info` parallels `temporal-host-info`: the worker charm **provides** the
namespace and task queue it serves so downstream charms know where to run workflows.

* Import :class:`TemporalWorkerInfoProvider` in the **temporal-worker** charm and
  instantiate it once; it publishes ``namespace`` and ``queue`` from config into each
  related application's relation data (leader only).

* Import :class:`TemporalWorkerInfoRequirer` in charms that relate to one or more workers.
  Use :meth:`TemporalWorkerInfoRequirer.is_ready` to decide when data is present; observe
  ``on.temporal_worker_info_available`` to react to updates. The importing charm should set
  unit status, not the library.
"""

import logging

from ops import (
    ConfigChangedEvent,
    EventBase,
    EventSource,
    Handle,
    Object,
    ObjectEvents,
    RelationChangedEvent,
    RelationJoinedEvent,
)
from ops.charm import CharmBase
from ops.model import Relation

# The unique Charmhub library identifier, never change it
LIBID = "75e7fa5301634bb9918f52ec0bd66c3a"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

RELATION_NAME = "temporal-worker-info"

logger = logging.getLogger(__name__)


class TemporalWorkerInfoProvider(Object):
    """Publish namespace and queue on the temporal-worker-info interface (provider side)."""

    def __init__(self, charm: CharmBase):
        """Create a new instance of the TemporalWorkerInfoProvider class.

        Args:
            charm: The charm that is using this interface.
        """
        super().__init__(charm, "worker-info-provider")
        self.charm = charm

        charm.framework.observe(charm.on[RELATION_NAME].relation_joined, self._on_worker_info_changed)
        charm.framework.observe(charm.on[RELATION_NAME].relation_changed, self._on_worker_info_changed)
        charm.framework.observe(charm.on.config_changed, self._on_config_changed)

    def _on_worker_info_changed(self, event: RelationChangedEvent | RelationJoinedEvent) -> None:
        """Update relation data.

        Args:
            event: The relation event that triggered this handler.
        """
        logger.info("Handling temporal-worker-info relation event")
        if self.charm.unit.is_leader():
            event.relation.data[self.charm.app]["namespace"] = str(self.charm.config["namespace"])
            event.relation.data[self.charm.app]["queue"] = str(self.charm.config["queue"])

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle config changes by updating relation data.

        Args:
            event: The config changed event that triggered this handler.
        """
        logger.info("Config changed, updating temporal-worker-info relation data")
        if self.charm.unit.is_leader():
            for relation in self.charm.model.relations.get(RELATION_NAME, []):
                relation.data[self.charm.app]["namespace"] = str(self.charm.config["namespace"])
                relation.data[self.charm.app]["queue"] = str(self.charm.config["queue"])


class TemporalWorkerInfoRelationReadyEvent(EventBase):
    """Event emitted when temporal-worker-info relation is ready for one relation.

    Attributes:
        namespace: Temporal namespace from the provider application's relation data.
        queue: Task queue name from the provider application's relation data.
        relation_id: Juju relation id for this event source, if multiple relations exist.
    """

    def __init__(
        self,
        handle: Handle,
        namespace: str,
        queue: str,
        relation_id: int | None = None,
    ):
        """Initialize temporal-worker-info ready event.

        Args:
            handle: Event handle.
            namespace: Temporal namespace from relation data.
            queue: Worker queue from relation data.
            relation_id: Juju relation id when multiple worker relations exist.
        """
        super().__init__(handle)
        self.namespace = namespace
        self.queue = queue
        self.relation_id = relation_id

    def snapshot(self) -> dict[str, str | int | None]:
        """Serialize event state for the framework.

        Returns:
            Mapping with ``namespace``, ``queue``, and optional ``relation_id`` keys.
        """
        return {"namespace": self.namespace, "queue": self.queue, "relation_id": self.relation_id}

    def restore(self, snapshot: dict[str, str | int | None]) -> None:
        """Restore event state from a snapshot.

        Args:
            snapshot: Data previously returned by :meth:`snapshot`.
        """
        self.namespace = str(snapshot["namespace"])
        self.queue = str(snapshot["queue"])
        raw_rid = snapshot.get("relation_id")
        self.relation_id = int(raw_rid) if raw_rid is not None else None


class TemporalWorkerInfoRequirerCharmEvents(ObjectEvents):
    """Events for the temporal-worker-info requirer.

    Attributes:
        temporal_worker_info_available: Fired when provider data is present for a relation.
    """

    temporal_worker_info_available = EventSource(TemporalWorkerInfoRelationReadyEvent)


class TemporalWorkerInfoRequirer(Object):
    """Requirer side: read namespace/queue published by temporal-worker (one or more relations).

    Attributes:
        on: Custom events for this relation interface.
        charm: The requirer :class:`~ops.charm.CharmBase` instance.
        relations: All ``temporal-worker-info`` :class:`~ops.model.Relation` instances for this charm.
        namespace: First complete namespace from a related worker; use :meth:`relation_payloads` if
            multiple workers are related.
        queue: Task queue matching :attr:`namespace` from the same relation.
    """

    on = TemporalWorkerInfoRequirerCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(self, charm: CharmBase):
        """Create a new instance of the TemporalWorkerInfoRequirer class.

        Args:
            charm: The charm that is using this interface.
        """
        super().__init__(charm, "worker-info-requirer")
        self.charm = charm
        charm.framework.observe(charm.on[RELATION_NAME].relation_joined, self._on_worker_info_relation_changed)
        charm.framework.observe(charm.on[RELATION_NAME].relation_changed, self._on_worker_info_relation_changed)

    @property
    def relations(self) -> list[Relation]:
        """Return all Juju relations for this interface name.

        Returns:
            List of :class:`~ops.model.Relation` instances (may be empty).
        """
        return self.charm.model.relations.get(RELATION_NAME, [])

    def is_ready(self, relation_id: int | None = None) -> bool:
        """Return whether namespace and queue are present in relation data.

        Args:
            relation_id: If set, only that relation is checked. If ``None``, return
                ``True`` when at least one related application has both keys set.

        Returns:
            ``True`` if the requested scope has complete provider data.
        """
        if relation_id is not None:
            rel = self.charm.model.get_relation(RELATION_NAME, relation_id)
            if not rel or not rel.app:
                return False
            data = rel.data[rel.app]
            return "namespace" in data and "queue" in data
        for relation in self.relations:
            if relation and relation.app:
                data = relation.data[relation.app]
                if "namespace" in data and "queue" in data:
                    return True
        return False

    def relation_payloads(self) -> dict[int, dict[str, str]]:
        """Collect namespace and queue for every relation that has both keys.

        Returns:
            Mapping from relation id to ``{"namespace": ..., "queue": ...}``.
        """
        out: dict[int, dict[str, str]] = {}
        for relation in self.relations:
            if not relation or not relation.app:
                continue
            data = relation.data[relation.app]
            namespace = data.get("namespace")
            queue = data.get("queue")
            if namespace is not None and queue is not None:
                out[relation.id] = {"namespace": str(namespace), "queue": str(queue)}
        return out

    def get_namespace_queue(self, relation_id: int) -> tuple[str | None, str | None]:
        """Return namespace and queue for a specific relation id.

        Args:
            relation_id: Juju id of the ``temporal-worker-info`` relation instance.

        Returns:
            ``(namespace, queue)`` from the remote application's data bag, or
            ``(None, None)`` if the relation is missing or incomplete.
        """
        rel = self.charm.model.get_relation(RELATION_NAME, relation_id)
        if not rel or not rel.app:
            return None, None
        data = rel.data[rel.app]
        return data.get("namespace"), data.get("queue")

    @property
    def namespace(self) -> str | None:
        """Namespace from the first related worker that has both keys set.

        Returns:
            Namespace string, or ``None`` if no relation has complete data. For multiple
            workers use :meth:`relation_payloads` or :meth:`get_namespace_queue`.
        """
        for relation in self.relations:
            namespace, _ = self.get_namespace_queue(relation.id)
            if namespace is not None:
                return namespace
        return None

    @property
    def queue(self) -> str | None:
        """Queue from the same relation as :attr:`namespace`.

        Returns:
            Queue string, or ``None`` if no relation has complete data.
        """
        for relation in self.relations:
            _, queue = self.get_namespace_queue(relation.id)
            if queue is not None:
                return queue
        return None

    def _on_worker_info_relation_changed(self, event: RelationChangedEvent) -> None:
        """Emit :attr:`on.temporal_worker_info_available` when this relation is complete.

        Args:
            event: Relation joined or changed event for ``temporal-worker-info``.
        """
        if not self.is_ready(event.relation.id):
            return
        namespace, queue = self.get_namespace_queue(event.relation.id)
        self.on.temporal_worker_info_available.emit(
            namespace=namespace,
            queue=queue,
            relation_id=event.relation.id,
        )
