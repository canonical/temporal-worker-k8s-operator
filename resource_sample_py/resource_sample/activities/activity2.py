# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os

from common.messages import ComposeGreetingInput
from temporalio import activity

# Basic activity that logs and does string concatenation
@activity.defn(name="vault_test")
async def vault_test(arg: ComposeGreetingInput) -> str:
    activity.logger.info("Running activity with parameter %s" % arg)

    sensitive1 = os.getenv("vault-secret1")
    sensitive2 = os.getenv("vault-secret2")
    
    return f"{sensitive1} {sensitive2}"
