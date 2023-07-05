# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import dataclass

@dataclass
class ComposeGreetingInput:
    greeting: str
    name: str
