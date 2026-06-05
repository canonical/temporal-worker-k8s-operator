# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define the Vault relation."""

import logging
import tempfile
from pathlib import Path

from charms.vault_k8s.v0 import vault_kv
from ops import framework
from ops.model import ModelError

from log import log_event_handler
from vault.client import VaultClient

logger = logging.getLogger(__name__)

VAULT_NONCE_SECRET_LABEL = "nonce"  # nosec
VAULT_CA_CERT_FILENAME = "ca.pem"
VAULT_CA_CERT_DIR_NAME = "temporal-worker-k8s-vault"


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

    def update_vault_relation(self):
        """Update Vault relation binding."""
        binding = self.charm.model.get_binding("vault")
        if binding is not None:
            try:
                egress_subnet = str(binding.network.interfaces[0].subnet)
                relation = self.charm.model.get_relation("vault")
                self.charm.vault.request_credentials(relation, egress_subnet, self.get_vault_nonce())
            except Exception as e:
                logger.warning(f"failed to update vault relation - {repr(e)}")

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
            "vault_ca_certificate": ca_certificate,
            "vault_role_id": role_id,
            "vault_role_secret_id": role_secret_id,
            "vault_mount": mount,
        }

    def get_vault_client(self):
        """Initialize Vault client.

        Returns:
            Vault client.
        """
        vault_config = self.get_vault_config()
        ca_certificate_path = self.write_ca_certificate(vault_config["vault_ca_certificate"])
        return VaultClient(
            address=vault_config["vault_address"],
            role_id=vault_config["vault_role_id"],
            role_secret_id=vault_config["vault_role_secret_id"],
            mount_point=vault_config["vault_mount"],
            cert_path=str(ca_certificate_path),
        )

    def write_ca_certificate(self, ca_certificate: str) -> Path:
        """Write the Vault CA certificate to ephemeral charm-local storage.

        The Vault relation data remains the source of truth. The file is recreated
        on demand because the charm container's runtime filesystem can disappear
        when the pod restarts.

        Args:
            ca_certificate: CA certificate received over the Vault relation.

        Returns:
            The CA certificate file path for clients that require one.

        Raises:
            ValueError: If the Vault relation has not provided a CA certificate.
        """
        if not ca_certificate:
            raise ValueError("vault relation: failed to get ca_certificate")

        ca_cert_dir = self._create_ca_certificate_dir()
        ca_cert_path = ca_cert_dir / VAULT_CA_CERT_FILENAME
        ca_cert_path.write_text(ca_certificate, encoding="utf-8")
        ca_cert_path.chmod(0o600)
        return ca_cert_path

    def _create_ca_certificate_dir(self) -> Path:
        """Create an ephemeral private directory for the Vault CA certificate.

        Returns:
            Path to the directory.
        """
        ca_cert_dir = Path(tempfile.gettempdir()) / VAULT_CA_CERT_DIR_NAME
        ca_cert_dir.mkdir(mode=0o700, exist_ok=True)
        return ca_cert_dir
