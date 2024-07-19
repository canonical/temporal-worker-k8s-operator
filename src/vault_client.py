# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Vault client class."""

import hvac


class VaultClient:
    """A client to interact with HashiCorp Vault.

    This client handles authentication using AppRole and provides methods to read and write secrets.

    Attributes:
        client (hvac.Client): An instance of the hvac Client.
    """

    def __init__(self, address: str, cert_path: str, role_id: str, role_secret_id: str, mount_point: str):
        """Initialize the VaultClient with the specified parameters.

        Args:
            address (str): The URL of the Vault server.
            cert_path (str): Path to the certificate file for SSL verification.
            role_id (str): The AppRole ID for authentication.
            role_secret_id (str): The AppRole Secret ID for authentication.
            mount_point (str): The mount point for the secret engine.
        """
        self.client = hvac.Client(
            url=address,
            verify=cert_path,
        )
        self._authenticate(role_id, role_secret_id)

    def _authenticate(self, role_id: str, role_secret_id: str):
        """Authenticate the client using the AppRole method.

        Args:
            role_id (str): The AppRole ID for authentication.
            role_secret_id (str): The AppRole Secret ID for authentication.

        Raises:
            Exception: If authentication fails.
        """
        self.client.auth.approle.login(
            role_id=role_id,
            secret_id=role_secret_id,
        )

        if not self.client.is_authenticated():
            raise Exception("Vault authentication failed.")

    def read_secret(self, path: str, key: str):
        """Read a secret from Vault at the given path and returns the value for the specified key.

        Args:
            path (str): The path to the secret in Vault.
            key (str): The key within the secret data to retrieve.

        Returns:
            str: The value of the specified key.

        Raises:
            Exception: If the path is invalid or the key is not found.
        """
        try:
            secret = self.client.secrets.kv.read_secret_version(path=path)
            return secret["data"]["data"][key]
        except hvac.exceptions.InvalidPath as e:
            raise Exception(f"Invalid path: {path}") from e
        except KeyError as e:
            raise Exception(f"Key '{key}' not found in path: {path}") from e

    def write_secret(self, path: str, data: dict):
        """Write a secret to Vault at the given path.

        Args:
            path (str): The path to the secret in Vault.
            data (dict): A dictionary containing the secret data to write.

        Raises:
            Exception: If the write operation fails.
        """
        try:
            self.client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
        except Exception as e:
            raise Exception(f"Failed to write secret: {str(e)}") from e
