#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker status checker."""


import sys


def check_worker_status():
    """Check Temporal worker status by reading status file."""
    try:
        with open("worker_status.txt", "r") as status_file:
            status = status_file.read().strip()
            print(f"Async status: {status}")

        if "Error" in status:
            exit_code = 1
        else:
            exit_code = 0
    except FileNotFoundError:
        print("Status file not found. Worker is not running.")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    check_worker_status()
