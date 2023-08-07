#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client worker."""

import asyncio
import glob
import inspect
import json
import os
import sys
from importlib import import_module

import sentry_sdk
from sentry_interceptor import SentryInterceptor
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


def _import_modules(module_type, module_name, supported_modules):
    """Extract supported workflows and activities .

    Args:
        module_type: "workflows" or "activities".
        module_name: Parent module name extracted from wheel file.
        supported_modules: list of supported modules to be extracted from module file.

    Returns:
        List of supported module references extracted from .py file.
    """
    folder_name = "user_provided"
    folder_path = os.path.join(os.getcwd(), folder_name, module_name, module_type)
    sys.path.append(folder_path)
    file_names = glob.glob(f"{folder_path}/*.py")
    file_names = [os.path.basename(file) for file in file_names]

    module_list = []
    for file_name in file_names:
        module_name = file_name[:-3]
        module = import_module(module_name)

        if "all" in supported_modules:
            for _, obj in inspect.getmembers(module):
                if module_type == "workflows":
                    if inspect.isclass(obj) and inspect.getmodule(obj) is module:
                        module_list.append(obj)
                else:
                    if inspect.isfunction(obj) and inspect.getmodule(obj) is module:
                        module_list.append(obj)
        else:
            for sm in supported_modules:
                if hasattr(module, sm):
                    module_list.append(getattr(module, sm))

    return module_list


async def run_worker(charm_config, supported_workflows, supported_activities, module_name):
    """Connect Temporal worker to Temporal server.

    Args:
        charm_config: Charm config containing worker options.
        supported_workflows: Comma-separated list of workflows supported by the worker.
        supported_activities: Comma-separated list of activities supported by the worker.
        module_name: Parent module name extracted from wheel file.
    """
    client_config = Options(
        host=charm_config["host"],
        namespace=charm_config["namespace"],
        queue=charm_config["queue"],
    )

    workflows = _import_modules("workflows", module_name=module_name, supported_modules=supported_workflows)
    activities = _import_modules("activities", module_name=module_name, supported_modules=supported_activities)

    if charm_config["tls-root-cas"].strip() != "":
        client_config.tls_root_cas = charm_config["tls-root-cas"]

    if charm_config["auth-enabled"]:
        client_config.auth = AuthOptions(provider=charm_config["auth-provider"], config=_get_auth_header(charm_config))

    if charm_config["encryption-key"].strip() != "":
        client_config.encryption = EncryptionOptions(key=charm_config["encryption-key"], compress=True)

    interceptors = []
    dsn = charm_config["sentry-dsn"].strip()
    if dsn != "":
        interceptors = [SentryInterceptor()]
        sentry_sdk.init(
            dsn=dsn,
            release=charm_config["sentry-release"].strip() or None,
            environment=charm_config["sentry-environment"].strip() or None,
        )

    client = await Client.connect(client_config)

    worker = Worker(
        client,
        task_queue=charm_config["queue"],
        workflows=workflows,
        activities=activities,
        interceptors=interceptors,
    )
    await worker.run()


if __name__ == "__main__":  # pragma: nocover
    cfg = json.loads(sys.argv[1])
    state_workflows = sys.argv[2].split(",")
    state_activities = sys.argv[3].split(",")
    mn = sys.argv[4]

    asyncio.run(run_worker(cfg, state_workflows, state_activities, mn))
