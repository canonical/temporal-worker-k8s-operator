#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client worker."""

import asyncio
import logging

from activities.activity1 import compose_greeting
from activities.activity2 import vault_test
from activities.db_activity import database_test
from activities.workload_metrics import metrics_test
from prometheus_client import start_http_server
from temporallib.client import Client, Options
from temporallib.encryption import EncryptionOptions
from temporallib.worker import SentryOptions, Worker, WorkerOptions
from workflows.workflow1 import DatabaseWorkflow, GreetingWorkflow, VaultWorkflow, WorkloadMetricsWorkflow

logger = logging.getLogger(__name__)


async def run_worker(metrics_port=10080):
    """Connect Temporal worker to Temporal server."""
    client = await Client.connect(
        client_opt=Options(encryption=EncryptionOptions()),
    )

    worker = Worker(
        client=client,
        workflows=[GreetingWorkflow, VaultWorkflow, DatabaseWorkflow, WorkloadMetricsWorkflow],
        activities=[compose_greeting, vault_test, database_test, metrics_test],
        worker_opt=WorkerOptions(sentry=SentryOptions()),
    )

    start_http_server(metrics_port)

    await worker.run()


if __name__ == "__main__":  # pragma: nocover
    asyncio.run(run_worker())
