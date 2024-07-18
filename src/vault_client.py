# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Vault client class."""

import os

import hvac


class VaultClient:
    def __init__(self, address: str, cert_path: str, role_id: str, role_secret_id: str, mount_point: str):
        self.client = hvac.Client(
            url=address,
            verify=cert_path,
        )
        self._authenticate(role_id, role_secret_id)

    def _authenticate(self, role_id: str, role_secret_id: str):
        self.client.auth.approle.login(
            role_id=role_id,
            secret_id=role_secret_id,
        )

        if not self.client.is_authenticated():
            raise Exception("Vault authentication failed.")

    def read_secret(self, path: str, key: str):
        try:
            secret = self.client.secrets.kv.read_secret_version(path=path)
            return secret["data"]["data"][key]
        except hvac.exceptions.InvalidPath:
            raise Exception(f"Invalid path: {path}")
        except KeyError:
            raise Exception(f"Key '{key}' not found in path: {path}")

    def write_secret(self, path: str, data: dict):
        try:
            self.client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
        except Exception as e:
            raise Exception(f"Failed to write secret: {str(e)}")
