from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import FailureError

from pathlib import Path
import sys
path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))

with workflow.unsafe.imports_passed_through():
    import resource_sample.activities.activity1 as all_activities
from datetime import timedelta

# Basic workflow that logs and invokes an activity
@workflow.defn(name="GreetingWorkflow")
class GreetingWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        workflow.logger.info("Running workflow with parameter %s" % name)
        return await workflow.execute_activity(
            all_activities.compose_greeting,
            all_activities.ComposeGreetingInput("Hello", name),
            start_to_close_timeout=timedelta(seconds=10),
        )