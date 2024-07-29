# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Vault actions class."""

import logging

from ops import framework

from log import log_event_handler

logger = logging.getLogger(__name__)


class VaultActions(framework.Object):
    """Client for vault actions."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "vault-actions")
        self.charm = charm

        charm.framework.observe(charm.on.add_vault_secret_action, self._on_add_vault_secret)
        charm.framework.observe(charm.on.get_vault_secret_action, self._on_get_vault_secret)

    @log_event_handler(logger)
    def _on_add_vault_secret(self, event):
        """Add Vault secret action handler.

        Args:
            event:The event triggered by the restart action
        """
        try:
            self._validate_vault_relation()
        except Exception as e:
            event.fail(str(e))

        path, key, value = (event.params.get(param) for param in ["path", "key", "value"])
        if not all([path, key, value]):
            event.fail("`path`, `key` and `value` are required parameters")

        try:
            vault_client = self.charm.vault_relation.get_vault_client()
        except Exception:
            event.fail("Unable to initialize vault client. remove relation and retry.")

        try:
            vault_client.write_secret(path=path, key=key, value=value)
            self.charm._update(event)
        except ValueError as e:
            logger.error("Unable to create secret in vault: %s", str(e))
            event.fail(str(e))
            return

        event.set_results({"result": "secret successfully created"})

    @log_event_handler(logger)
    def _on_get_vault_secret(self, event):
        """Get Vault secret action handler.

        Args:
            event:The event triggered by the restart action
        """
        try:
            self._validate_vault_relation()
        except Exception as e:
            event.fail(str(e))

        path, key = (event.params.get(param) for param in ["path", "key"])
        if not all([path, key]):
            event.fail("`path` and `key` are required parameters")

        try:
            vault_client = self.charm.vault_relation.get_vault_client()
        except Exception as e:
            logger.error("Unable to initialize vault client: %s", e)
            event.fail("Unable to initialize vault client. Remove relation and retry.")
            return

        try:
            value = vault_client.read_secret(path=path, key=key)
        except Exception as e:
            logger.error(f"Unable to read vault secret `{key}` at path `{path}`: {e}")
            event.fail(f"Unable to read vault secret `{key}` at path `{path}`: {e}")
            return

        event.set_results({"result": value})

    def _validate_vault_relation(self):
        """Validate Vault relation.

        Raises:
            Exception: if the Vault relation was not successfully validated.
        """
        container = self.charm.unit.get_container(self.charm.name)
        if not container.can_connect():
            raise Exception("Failed to connect to the container")

        if not self.charm.model.relations["vault"]:
            raise Exception("No vault relation found")
