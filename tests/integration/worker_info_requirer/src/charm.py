# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""K8s charm for testing."""

import logging

import ops
from charms.temporal_worker_k8s.v0 import temporal_worker_info

logger = logging.getLogger(__name__)

CONTAINER = "workload"


class Charm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        """Initialize charm and observe relevant events.

        Args:
            framework: The framework instance for this charm.
        """
        super().__init__(framework)
        framework.observe(self.on[CONTAINER].pebble_ready, self._configure)
        self.worker_info = temporal_worker_info.TemporalWorkerInfoRequirer(self)
        framework.observe(self.worker_info.on.temporal_worker_info_available, self._configure)

    def _configure(self, event: ops.EventBase):
        """Set unit status based on temporal-worker-info data availability.

        Args:
            event: The event that triggered reconfiguration.
        """
        if self.worker_info.namespace is None or self.worker_info.queue is None:
            self.unit.status = ops.WaitingStatus("Waiting for temporal-worker-info relation data")
            return
        self.unit.status = ops.ActiveStatus(
            f"Temporal namespace: {self.worker_info.namespace}, queue: {self.worker_info.queue}"
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main(Charm)
