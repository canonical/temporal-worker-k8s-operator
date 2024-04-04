#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker status checker."""


import logging
import sys

logger = logging.getLogger(__name__)


def check_worker_status():
    """Check Temporal worker status by reading status file."""
    try:
        with open("worker_status.txt", "r") as status_file:
            status = status_file.read().strip()
            logger.info(f"Async status: {status}")

        if status.startswith("Success"):
            exit_code = 0
        else:
            exit_code = 1
    except FileNotFoundError:
        logger.error("Status file not found. Worker is not running.")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    check_worker_status()
