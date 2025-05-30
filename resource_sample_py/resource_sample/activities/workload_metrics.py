# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from temporalio import activity

from prometheus_client import Gauge

# Metric that tracks the number of calls to the activity.
EXECUTION_COUNT = Gauge("activity_execution_count", "Execution count")

# Basic activity that increments a metric.
@activity.defn(name="metrics_test")
async def metrics_test() -> str:
    activity.logger.info("Running activity")
    EXECUTION_COUNT.inc(1)
    return "hello world"
