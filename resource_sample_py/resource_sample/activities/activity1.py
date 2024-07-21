# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from common.messages import ComposeGreetingInput
from temporalio import activity
import os


# Basic activity that logs and does string concatenation
@activity.defn(name="compose_greeting")
async def compose_greeting(arg: ComposeGreetingInput) -> str:
    activity.logger.info("Running activity with parameter %s" % arg)
    env_var = os.getenv("message")    
    juju_secret1 = os.getenv("juju-secret1")
    
    return f"{env_var} {juju_secret1}"
