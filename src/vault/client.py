# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Vault client class."""

import logging

import hvac

logger = logging.getLogger(__name__)


class VaultOperationError(Exception):
    """Exception raised for errors in the vault operations."""


class VaultClient:
    """A client to interact with HashiCorp Vault.

    This client handles authentication using AppRole and provides methods to read and write secrets.

    Attributes:
        client (hvac.Client): An instance of the hvac Client.
    """

    def __init__(self, address: str, cert_path: str, role_id: str, role_secret_id: str, mount_point: str):
        """Initialize the VaultClient with the specified parameters.

        Args:
            address: The URL of the Vault server.
            cert_path: Path to the certificate file for SSL verification.
            role_id: The AppRole ID for authentication.
            role_secret_id: The AppRole Secret ID for authentication.
            mount_point: The mount point for the secret engine.
        """
        self.client = hvac.Client(
            url=address,
            verify=cert_path,
        )
        self.mount_point = mount_point
        self._authenticate(role_id, role_secret_id)

    def _authenticate(self, role_id: str, role_secret_id: str):
        """Authenticate the client using the AppRole method.

        Args:
            role_id: The AppRole ID for authentication.
            role_secret_id: The AppRole Secret ID for authentication.

        Raises:
            Exception: If authentication fails.
        """
        login_response = self.client.auth.approle.login(
            role_id=role_id,
            secret_id=role_secret_id,
            use_token=False,
        )

        self.client.token = login_response["auth"]["client_token"]

        if not self.client.is_authenticated():
            raise Exception("Vault authentication failed.")

    def read_secret(self, path: str, key: str):
        """Read a secret from Vault at the given path and returns the value for the specified key.

        Args:
            path: The path to the secret in Vault.
            key: The key within the secret data to retrieve.

        Returns:
            str: The value of the specified key.

        Raises:
            Exception: If the operation fails.
        """
        try:
            secret = self.client.secrets.kv.v2.read_secret(path=path, mount_point=self.mount_point)
            return secret["data"]["data"][key]
        except Exception as e:
            raise Exception(f"Could not fetch from Vault: {e}") from e

    def write_secret(self, path: str, key: str, value: str):
        """Write a secret to Vault at the given path.

        If a secret exists at the specified path, the new key is appended to it, or
        it updates the value if the key already exists.

        Args:
            path: The path to the secret in Vault.
            key: Key to store in Vault.
            value: Value to store in Vault.

        Raises:
            VaultOperationError: If the operation fails.
        """
        try:
            self.client.secrets.kv.v2.patch(path=path, secret={key: value}, mount_point=self.mount_point)
            return
        except hvac.exceptions.InvalidPath:
            logger.info("Secret %s does not yet exist on path %s", key, path)

        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path, secret={key: value}, mount_point=self.mount_point
            )
        except Exception as e:
            raise VaultOperationError(f"Vault write operation failed: {e}") from e
