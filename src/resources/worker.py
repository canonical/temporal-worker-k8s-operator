#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client worker."""

import asyncio
import json
import sys

from temporal_client.activities import compose_greeting
from temporal_client.workflows import GreetingWorkflow
from temporalio.worker import Worker
from temporallib.auth import (
    AuthOptions,
    GoogleAuthOptions,
    KeyPair,
    MacaroonAuthOptions,
)
from temporallib.client import Client, Options
from temporallib.encryption import EncryptionOptions


def _get_auth_header(charm_config):
    """Get auth options based on provider.

    Args:
        charm_config: Charm config containing worker options.

    Returns:
        AuthOptions object.
    """
    if charm_config["auth-provider"] == "candid":
        return MacaroonAuthOptions(
            keys=KeyPair(private=charm_config["candid-private-key"], public=charm_config["candid-public-key"]),
            macaroon_url=charm_config["candid-url"],
            username=charm_config["candid-username"],
        )

    if charm_config["auth-provider"] == "google":
        return GoogleAuthOptions(
            type="service_account",
            project_id=charm_config["oidc-project-id"],
            private_key_id=charm_config["oidc-private-key-id"],
            private_key=charm_config["oidc-private-key"],
            client_email=charm_config["oidc-client-email"],
            client_id=charm_config["oidc-client-id"],
            auth_uri=charm_config["oidc-auth-uri"],
            token_uri=charm_config["oidc-token-uri"],
            auth_provider_x509_cert_url=charm_config["oidc-auth-cert-url"],
            client_x509_cert_url=charm_config["oidc-client-cert-url"],
        )

    return None


async def run_worker(charm_config):
    """Connect Temporal worker to Temporal server.

    Args:
        charm_config: Charm config containing worker options.
    """
    client_config = Options(
        host=charm_config["host"],
        namespace=charm_config["namespace"],
        queue=charm_config["queue"],
    )

    if charm_config["tls-root-cas"].strip() != "":
        client_config.tls_root_cas = charm_config["tls-root-cas"]

    if charm_config["auth-enabled"]:
        client_config.auth = AuthOptions(provider=charm_config["auth-provider"], config=_get_auth_header(charm_config))

    if charm_config["encryption-key"].strip() != "":
        client_config.encryption = EncryptionOptions(key=charm_config["encryption-key"])

    client = await Client.connect(client_config)

    worker = Worker(
        client,
        task_queue=charm_config["queue"],
        workflows=[GreetingWorkflow],
        activities=[compose_greeting],
    )
    await worker.run()


if __name__ == "__main__":  # pragma: nocover
    cfg = json.loads(sys.argv[1])
    asyncio.run(run_worker(cfg))
