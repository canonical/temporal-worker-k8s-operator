# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Vault relation."""

import logging

from charms.vault_k8s.v0 import vault_kv
from ops import framework
from ops.model import ModelError

from log import log_event_handler

logger = logging.getLogger(__name__)

VAULT_NONCE_SECRET_LABEL = "nonce"  # nosec
VAULT_CERT_PATH = "/vault/cert.pem"


class VaultRelation(framework.Object):
    """Client for vault relation."""

    def __init__(self, charm):
        """Construct.

        Args:
            charm: The charm to attach the hooks to.
        """
        super().__init__(charm, "vault")
        self.charm = charm

        charm.framework.observe(charm.vault.on.connected, self._on_vault_connected)
        charm.framework.observe(charm.vault.on.ready, self._on_vault_ready)
        charm.framework.observe(charm.vault.on.gone_away, self._on_vault_gone_away)

    @log_event_handler(logger)
    def _on_vault_connected(self, event: vault_kv.VaultKvConnectedEvent):
        """Handle Vault connected event.

        Args:
            event: The event triggered when the Vault connection is created.
        """
        relation = self.charm.model.get_relation(event.relation_name, event.relation_id)
        egress_subnet = str(self.charm.model.get_binding(relation).network.interfaces[0].subnet)
        self.charm.vault.request_credentials(relation, egress_subnet, self.get_vault_nonce())

    @log_event_handler(logger)
    def _on_vault_ready(self, event: vault_kv.VaultKvReadyEvent):
        """Handle Vault ready event.

        Args:
            event: The event triggered when the Vault connection is ready.
        """
        self.charm._update(event)

    @log_event_handler(logger)
    def _on_vault_gone_away(self, event: vault_kv.VaultKvGoneAwayEvent):
        """Handle Vault removed event.

        Args:
            event: The event triggered when the Vault connection is removed.
        """
        self.charm._update(event)

    def get_vault_nonce(self):
        """Retrieve the Vault nonce.

        Returns:
            The nonce retrieved from the secret storage.

        Raises:
            ModelError: If secret is not found.
        """
        try:
            secret = self.charm.model.get_secret(label=VAULT_NONCE_SECRET_LABEL)
            nonce = secret.get_content(refresh=True)["nonce"]
            return nonce
        except ModelError as e:
            logger.debug(f"Secret {VAULT_NONCE_SECRET_LABEL} not found: {e}")
            raise ModelError from e

    def get_vault_config(self):
        """Retrieve Vault configuration details.

        Returns:
            A dictionary containing Vault configuration details if it exists.

        Raises:
            ValueError: if unit_credentials were not successfully fetched.
        """
        relation = self.charm.model.get_relation("vault")
        if relation is None:
            logger.debug("No vault relation found")
            return None
        vault_url = self.charm.vault.get_vault_url(relation)
        ca_certificate = self.charm.vault.get_ca_certificate(relation)
        mount = self.charm.vault.get_mount(relation)
        unit_credentials = self.charm.vault.get_unit_credentials(relation)
        if not unit_credentials:
            raise ValueError("vault relation: failed to get unit_credentials")

        # unit_credentials is a juju secret id
        secret = self.charm.model.get_secret(id=unit_credentials)
        secret_content = secret.get_content(refresh=True)
        role_id = secret_content["role-id"]
        role_secret_id = secret_content["role-secret-id"]

        return {
            "vault_address": vault_url,
            "vault_ca_certificate_bytes": ca_certificate,
            "vault_role_id": role_id,
            "vault_role_secret_id": role_secret_id,
            "vault_mount": mount,
            "vault_cert_path": VAULT_CERT_PATH,
        }
