#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client worker."""

import asyncio
import glob
import inspect
import os
import sys
from importlib import import_module

from temporallib.auth import (
    AuthOptions,
    GoogleAuthOptions,
    KeyPair,
    MacaroonAuthOptions,
)
from temporallib.client import Client, Options
from temporallib.encryption import EncryptionOptions
from temporallib.worker import SentryOptions, Worker, WorkerOptions


def _get_auth_header():
    """Get auth options based on provider.

    Returns:
        AuthOptions object.
    """
    if os.getenv("TWC_AUTH_PROVIDER") == "candid":
        return MacaroonAuthOptions(
            keys=KeyPair(private=os.getenv("TWC_CANDID_PRIVATE_KEY"), public=os.getenv("TWC_CANDID_PUBLIC_KEY")),
            macaroon_url=os.getenv("TWC_CANDID_URL"),
            username=os.getenv("TWC_CANDID_USERNAME"),
        )

    if os.getenv("TWC_AUTH_PROVIDER") == "google":
        return GoogleAuthOptions(
            type="service_account",
            project_id=os.getenv("TWC_OIDC_PROJECT_ID"),
            private_key_id=os.getenv("TWC_OIDC_PRIVATE_KEY_ID"),
            private_key=os.getenv("TWC_OIDC_PRIVATE_KEY"),
            client_email=os.getenv("TWC_OIDC_CLIENT_EMAIL"),
            client_id=os.getenv("TWC_OIDC_CLIENT_ID"),
            auth_uri=os.getenv("TWC_OIDC_AUTH_URI"),
            token_uri=os.getenv("TWC_OIDC_TOKEN_URI"),
            auth_provider_x509_cert_url=os.getenv("TWC_OIDC_AUTH_CERT_URL"),
            client_x509_cert_url=os.getenv("TWC_OIDC_CLIENT_CERT_URL"),
        )

    return None


def _import_modules(module_type, unpacked_file_name, module_name, supported_modules):
    """Extract supported workflows and activities .

    Args:
        module_type: "workflows" or "activities".
        unpacked_file_name: Name of unpacked wheel file.
        module_name: Parent module name extracted from wheel file.
        supported_modules: list of supported modules to be extracted from module file.

    Returns:
        List of supported module references extracted from .py file.
    """
    folder_path = os.path.join(os.getcwd(), unpacked_file_name, module_name, module_type)
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
                if hasattr(module, sm.strip()):
                    module_list.append(getattr(module, sm.strip()))

    return module_list


async def run_worker(unpacked_file_name, module_name):
    """Connect Temporal worker to Temporal server.

    Args:
        unpacked_file_name: Name of unpacked wheel file.
        module_name: Parent module name extracted from wheel file.
    """
    client_config = Options(
        host=os.getenv("TWC_HOST"),
        namespace=os.getenv("TWC_NAMESPACE"),
        queue=os.getenv("TWC_QUEUE"),
    )

    workflows = _import_modules(
        "workflows",
        unpacked_file_name=unpacked_file_name,
        module_name=module_name,
        supported_modules=os.getenv("TWC_SUPPORTED_WORKFLOWS").split(","),
    )
    activities = _import_modules(
        "activities",
        unpacked_file_name=unpacked_file_name,
        module_name=module_name,
        supported_modules=os.getenv("TWC_SUPPORTED_ACTIVITIES").split(","),
    )

    if os.getenv("TWC_TLS_ROOT_CAS").strip() != "":
        client_config.tls_root_cas = os.getenv("TWC_TLS_ROOT_CAS")

    if os.getenv("TWC_AUTH_PROVIDER").strip() != "":
        client_config.auth = AuthOptions(provider=os.getenv("TWC_AUTH_PROVIDER"), config=_get_auth_header())

    if os.getenv("TWC_ENCRYPTION_KEY").strip() != "":
        client_config.encryption = EncryptionOptions(key=os.getenv("TWC_ENCRYPTION_KEY"), compress=True)

    worker_opt = None
    dsn = os.getenv("TWC_SENTRY_DSN").strip()
    if dsn != "":
        sentry = SentryOptions(
            dsn=dsn,
            release=os.getenv("TWC_SENTRY_RELEASE").strip() or None,
            environment=os.getenv("TWC_SENTRY_ENVIRONMENT").strip() or None,
            redact_params=os.getenv("TWC_SENTRY_REDACT_PARAMS"),
        )

        worker_opt = WorkerOptions(sentry=sentry)

    client = await Client.connect(client_config)

    worker = Worker(
        client=client,
        task_queue=os.getenv("TWC_QUEUE"),
        workflows=workflows,
        activities=activities,
        worker_opt=worker_opt,
    )
    await worker.run()


if __name__ == "__main__":  # pragma: nocover
    global_unpacked_file_name = sys.argv[1]
    global_module_name = sys.argv[2]

    asyncio.run(run_worker(global_unpacked_file_name, global_module_name))
