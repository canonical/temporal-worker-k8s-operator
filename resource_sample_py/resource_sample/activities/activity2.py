# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os

import hvac
from common.messages import ComposeGreetingInput
from temporalio import activity

vault_client = None
if os.getenv("TWC_VAULT_ADDR"):
    vault_client = hvac.Client(
        url=os.getenv("TWC_VAULT_ADDR"),
        verify=os.getenv("TWC_VAULT_CERT_PATH"),
    )

    vault_client.auth.approle.login(
        role_id=os.getenv("TWC_VAULT_ROLE_ID"),
        secret_id=os.getenv("TWC_VAULT_ROLE_SECRET_ID"),
    )


# Basic activity that logs and does string concatenation
@activity.defn(name="vault_test")
async def vault_test(arg: ComposeGreetingInput) -> str:
    activity.logger.info("Running activity with parameter %s" % arg)

    hvac_secret = {
        "greeting": arg.greeting,
    }

    vault_client.secrets.kv.v2.create_or_update_secret(
        path="credentials",
        mount_point=os.getenv("TWC_VAULT_MOUNT"),
        secret=hvac_secret,
    )

    read_secret_result = vault_client.secrets.kv.v2.read_secret(
        path="credentials",
        mount_point=os.getenv("TWC_VAULT_MOUNT"),
    )

    greeting = read_secret_result["data"]["data"]["greeting"]
    return f"{greeting}, {arg.name}!"
