# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Relation management for temporal-worker-consumer interface."""

import logging

from ops import CharmEvents, RelationChangedEvent, RelationJoinedEvent, framework
from ops.charm import CharmBase

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
            charm.on.worker_consumer_relation_joined, self._on_worker_consumer_changed
        )
        charm.framework.observe(
            charm.on.worker_consumer_relation_changed, self._on_worker_consumer_changed
        )
        charm.framework.observe(charm.on.config_changed, self._on_worker_consumer_changed)

    def _on_worker_consumer_changed(self, event: RelationChangedEvent | RelationJoinedEvent):
        """Update relation data.

        :param: event: The relation event that triggered this handler.
        :type event: RelationChangedEvent | RelationJoinedEvent
        """
        logger.info('Handling temporal-worker-consumer relation event')
        if self.charm.unit.is_leader():
            # Config could have changed, so update all relations
            for relation in self.charm.model.relations.get('worker-consumer', ()):
                relation.data[self.charm.app]['namespace'] = str(self.charm.config['namespace'])
                relation.data[self.charm.app]['queue'] = str(self.charm.config['queue'])


class TemporalWorkerConsumerRelationReadyEvent(framework.EventBase):
    """Event emitted when worker-consumer relation is ready."""

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
        return {'namespace': self.namespace, 'queue': self.queue}

    def restore(self, snapshot: dict[str, str]) -> None:
        """Restore the event from a snapshot."""
        self.namespace = snapshot['namespace']
        self.queue = snapshot['queue']


class TemporalWorkerConsumerRequirerCharmEvents(CharmEvents):
    """List of events that the worker-consumer requirer charm can leverage."""

    worker_consumer_available = framework.EventSource(TemporalWorkerConsumerRelationReadyEvent)


class TemporalWorkerConsumerRequirer(framework.Object):
    """A class for managing the temporal-worker-consumer interface requirer.

    Track this relation in your charm with:

    .. code-block:: python

        self.worker_consumer = TemporalWorkerConsumerRequirer(self)
        # update container with new worker consumer info
        self.framework.observe(self.worker_consumer.on.worker_consumer_available, self._update)
    """
    on = TemporalWorkerConsumerRequirerCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(self, charm: CharmBase):
        """Create a new instance of the TemporalWorkerConsumerRequirer class.

        :param: charm: The charm that is using this interface.
        """
        super().__init__(charm, 'worker-consumer-requirer')
        self.charm = charm
        self.namespace: str | None = None
        self.queue: str | None = None
        charm.framework.observe(
            charm.on.worker_consumer_relation_joined, self._on_worker_consumer_relation_changed
        )
        charm.framework.observe(
            charm.on.worker_consumer_relation_changed, self._on_worker_consumer_relation_changed
        )

    def _on_worker_consumer_relation_changed(self, event: RelationChangedEvent):
        """Retrieve relation data and emit worker_consumer_available event.

        :param: event: The relation event that triggered this handler.
        :type event: RelationChangedEvent | RelationJoinedEvent
        """
        self.namespace = event.relation.data[event.relation.app]['namespace']
        self.queue = event.relation.data[event.relation.app]['queue']
        self.on.worker_consumer_available.emit(namespace=self.namespace, queue=self.queue)
