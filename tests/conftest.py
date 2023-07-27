# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for Temporal worker charm tests."""


def pytest_addoption(parser):
    """Parse additional pytest options.

    Args:
        parser: Pytest parser.
    """
    parser.addoption("--charm-file", action="store")
