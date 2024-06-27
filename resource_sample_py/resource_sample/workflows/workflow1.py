# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    import activities.activity1 as all_activities1
    import activities.activity2 as all_activities2


# Basic workflow that logs and invokes an activity
@workflow.defn(name="GreetingWorkflow")
class GreetingWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        workflow.logger.info("Running workflow with parameter %s" % name)
        return await workflow.execute_activity(
            all_activities1.compose_greeting,
            all_activities1.ComposeGreetingInput("Hello", name),
            start_to_close_timeout=timedelta(seconds=10),
        )


@workflow.defn(name="VaultWorkflow")
class VaultWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        workflow.logger.info("Running workflow with parameter %s" % name)
        return await workflow.execute_activity(
            all_activities2.vault_test,
            all_activities1.ComposeGreetingInput("Hello", name),
            start_to_close_timeout=timedelta(seconds=10),
        )
