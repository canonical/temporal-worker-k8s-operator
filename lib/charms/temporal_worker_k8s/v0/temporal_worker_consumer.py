# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from ops import ConfigChangedEvent, Handle, RelationChangedEvent, RelationJoinedEvent, framework
from ops.charm import CharmBase
from ops.framework import EventBase, EventSource, ObjectEvents
from ops.model import ActiveStatus, Relation, WaitingStatus

# The unique Charmhub library identifier, never change it
LIBID = "20f19c7f5637417d8703b53b5d500464"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

RELATION_NAME = 'temporal-worker-consumer'

logger = logging.getLogger(__name__)

class TemporalWorkerConsumerProvider(framework.Object):
    """A class for managing the temporal-worker-consumer interface provider."""

    def __init__(self, charm: CharmBase):
        """Create a new instance of the TemporalWorkerConsumerProvider class.

        :param: charm: The charm that is using this interface.
        """
        super().__init__(charm, 'worker-consumer-provider')
        self.charm = charm

        charm.framework.observe(
            charm.on[RELATION_NAME].relation_joined, self._on_worker_consumer_changed
        )
        charm.framework.observe(
            charm.on[RELATION_NAME].relation_changed, self._on_worker_consumer_changed
        )
        charm.framework.observe(charm.on.config_changed, self._on_config_changed)

    def _on_worker_consumer_changed(self, event: RelationChangedEvent | RelationJoinedEvent):
        """Update relation data.

        :param: event: The relation event that triggered this handler.
        :type event: RelationChangedEvent | RelationJoinedEvent
        """
        logger.info('Handling temporal-worker-consumer relation event')
        if self.charm.unit.is_leader():
            event.relation.data[self.charm.app]['namespace'] = str(self.charm.config['namespace'])
            event.relation.data[self.charm.app]['queue'] = str(self.charm.config['queue'])

    def _on_config_changed(self, event: ConfigChangedEvent):
        """Handle config changes by updating relation data.

        :param: event: The config changed event that triggered this handler.
        :type event: ConfigChangedEvent
        """
        logger.info('Config changed, updating temporal-worker-consumer relation data')
        if self.charm.unit.is_leader():
            # Config could have changed, so update all relations
            for relation in self.charm.model.relations.get(RELATION_NAME, ()):
                relation.data[self.charm.app]['namespace'] = str(self.charm.config['namespace'])
                relation.data[self.charm.app]['queue'] = str(self.charm.config['queue'])


class TemporalWorkerConsumerRelationReadyEvent(EventBase):
    """Event emitted when worker-consumer relation is ready."""

    def __init__(
        self,
        handle: Handle,
        namespace: str,
        queue: str,
    ):
        super().__init__(handle)
        self.namespace = namespace
        self.queue = queue

    def snapshot(self) -> dict[str, str]:
        """Return a snapshot of the event."""
        return {'namespace': self.namespace, 'queue': self.queue}

    def restore(self, snapshot: dict[str, str]) -> None:
        """Restore the event from a snapshot."""
        self.namespace = snapshot['namespace']
        self.queue = snapshot['queue']


class TemporalWorkerConsumerRequirerCharmEvents(ObjectEvents):
    """List of events that the worker-consumer requirer charm can leverage."""

    temporal_worker_consumer_available = EventSource(TemporalWorkerConsumerRelationReadyEvent)


class TemporalWorkerConsumerRequirer(framework.Object):
    """A class for managing the temporal-worker-consumer interface requirer.

    Track this relation in your charm with:

    .. code-block:: python

        self.worker_consumer = TemporalWorkerConsumerRequirer(self)
        # update container with new worker consumer info
        framework.observe(self.worker_consumer.on.temporal_worker_consumer_available, self._update)

        def _update(self, event):
            namespace = self.worker_consumer.namespace
            queue = self.worker_consumer.queue
    """

    on = TemporalWorkerConsumerRequirerCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(self, charm: CharmBase):
        """Create a new instance of the TemporalWorkerConsumerRequirer class.

        :param: charm: The charm that is using this interface.
        """
        super().__init__(charm, 'worker-consumer-requirer')
        self.charm = charm
        charm.framework.observe(
            charm.on[RELATION_NAME].relation_joined, self._on_worker_consumer_relation_changed
        )
        charm.framework.observe(
            charm.on[RELATION_NAME].relation_changed, self._on_worker_consumer_relation_changed
        )

    @property
    def relations(self) -> list[Relation]:
        """Return the relations for this interface."""
        return self.charm.model.relations.get(RELATION_NAME, [])

    @property
    def namespace(self) -> str | None:
        """Return the namespace from the relation data."""
        for relation in self.relations:
            if relation and relation.app:
                return relation.data[relation.app].get('namespace', None)
        return None

    @property
    def queue(self) -> str | None:
        """Return the queue from the relation data."""
        for relation in self.relations:
            if relation and relation.app:
                return relation.data[relation.app].get('queue', None)
        return None

    def _on_worker_consumer_relation_changed(self, event: RelationChangedEvent):
        """Retrieve relation data and emit worker_consumer_available event.

        :param: event: The relation event that triggered this handler.
        :type event: RelationChangedEvent | RelationJoinedEvent
        """
        try:
            namespace = event.relation.data[event.relation.app]['namespace']
            queue = event.relation.data[event.relation.app]['queue']
        except KeyError:
            self.charm.unit.status = WaitingStatus('Waiting for temporal-worker-consumer provider')
            event.defer()
            return
        self.charm.unit.status = ActiveStatus()
        self.on.temporal_worker_consumer_available.emit(namespace=namespace, queue=queue)
