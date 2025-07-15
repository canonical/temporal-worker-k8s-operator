# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Vault relation."""

import logging

from ops import framework, CharmBase
from ops.model import BlockedStatus

from log import log_event_handler

logger = logging.getLogger(__name__)

class WorkerConsumer(framework.Object):

    def __init__(self, charm: CharmBase):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "worker-consumer")
        self.charm = charm

        charm.framework.observe(charm.worker_consumer_relation_joined, self._on_worker_consumer_changed)
        charm.framework.observe(charm.worker_consumer_relation_changed, self._on_worker_consumer_changed)
        charm.framework.observe(charm.config_changed, self._on_worker_consumer_changed)

    @log_event_handler(logger)
    def _on_worker_consumer_changed(self, event):
        if self.charm.unit.is_leader():
            if host := self.charm._state.host:
                for relation in self.charm.model.relations.get("worker_consumer", ()):

                    relation.data[self.charm.app]["host"] = host
                    relation.data[self.charm.app]["namespace"] = self.charm.config["namespace"]
                    relation.data[self.charm.app]["queue"] = self.charm.config["queue"]
            else:
                self.unit.status = BlockedStatus("Waiting for host-info relation before processing worker-consumer relation.")
