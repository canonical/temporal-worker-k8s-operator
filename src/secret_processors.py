# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Secret config processors."""

import logging

import yaml
from ops.jujuversion import JujuVersion
from ops.model import ModelError, SecretNotFoundError

logger = logging.getLogger(__name__)


def process_env_variables(parsed_secrets_data):
    """Process environment variables from the parsed secrets data.

    Args:
        parsed_secrets_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing environment variables.
    """
    env_variables = parsed_secrets_data.get("env", {})
    return env_variables


def process_juju_secrets(charm, parsed_secrets_data):
    """Process Juju secrets from the parsed secrets data.

    Args:
        charm: The charm to perform operations on.
        parsed_secrets_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing Juju secrets.

    Raises:
        ValueError: If the Juju version does not support Juju user secrets,
                    if a specified Juju secret is not found,
                    or if the charm does not have permission to access the specified Juju secret.
    """
    charm_env = {}
    if parsed_secrets_data.get("juju") and not JujuVersion.from_environ().has_secrets:
        raise ValueError("Juju version does not support Juju user secrets")

    juju_variables = parsed_secrets_data.get("juju", [])
    for juju_secret in juju_variables:
        try:
            secret_id = juju_secret.get("secret-id")
            key = juju_secret.get("key")
            secret = charm.model.get_secret(id=secret_id)
            secret_content = secret.get_content(refresh=True)
            charm_env.update({key: secret_content[key]})
        except SecretNotFoundError as e:
            raise ValueError(f"Juju secret `{secret_id}` not found") from e
        except ModelError as e:
            raise ValueError(f"Access permission not granted to charm for secret `{secret_id}`") from e
        except KeyError as e:
            logger.error(f"Error parsing secrets env: {e}")
            raise ValueError(f"Error parsing secrets env: {e}") from e

    return charm_env


def process_vault_secrets(charm, parsed_secrets_data):
    """Process Vault secrets from the parsed secrets data.

    Args:
        charm: The charm to perform operations on.
        parsed_secrets_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing Vault secrets.

    Raises:
        ValueError: If there is no vault relation, if there is an error initializing the vault client,
                    or if there is an error reading a vault secret.
    """
    # TODO (kelkawi-a): Convert to using structured config
    charm_env = {}
    vault_variables = parsed_secrets_data.get("vault", [])

    if vault_variables and not charm.model.relations["vault"]:
        raise ValueError("No vault relation found to fetch secrets from")

    if vault_variables and charm.model.relations["vault"]:
        try:
            vault_client = charm.vault_relation.get_vault_client()
        except Exception as e:
            logger.error("Unable to initialize vault client: %s", e)
            raise ValueError("Unable to initialize vault client. Remove relation and retry.") from e

        for item in vault_variables:
            key = item.get("key")
            path = item.get("path")
            try:
                secret = vault_client.read_secret(path=path, key=key)
            except Exception as e:
                raise ValueError(f"Unable to read vault secret `{key}` at path `{path}`: {e}") from e
            charm_env.update({key: secret})

    return charm_env


def parse_secrets(yaml_string):
    """Parse a YAML string containing secrets and validates its structure.

    The YAML string should contain a 'secrets' key with nested 'env', 'juju', and 'vault' keys.
    Each nested key should follow a specific structure:
        - 'env': A list of single-key dictionaries.
        - 'juju': A list of dictionaries with 'secret-id' and 'key' keys.
        - 'vault': A list of dictionaries with 'path' and 'key' keys.

    Args:
        yaml_string: The YAML string to be parsed.

    Returns:
        dict: A dictionary with the parsed and validated secrets.
              The structure of the returned dictionary is:
              {
                  "env": {str: str},
                  "juju": [{"secret-id": str, "key": str}],
                  "vault": [{"path": str, "key": str}]
              }

    Raises:
        ValueError: If the YAML string does not conform to the expected structure.
    """
    data = yaml.safe_load(yaml_string)

    # Validate the main structure
    if not isinstance(data, dict) or "secrets" not in data:
        raise ValueError("Invalid secrets structure: 'secrets' key not found")

    secrets_key = data["secrets"]
    if not isinstance(secrets_key, dict):
        raise ValueError("Invalid secrets structure: 'secrets' should be a dictionary")

    # Validate env key
    env = secrets_key.get("env", [])
    if not isinstance(env, list) or not all(isinstance(item, dict) and len(item) == 1 for item in env):
        raise ValueError("Invalid secrets structure: 'env' should be a list of single-key dictionaries")

    # Validate juju key
    juju = secrets_key.get("juju", [])
    if not isinstance(juju, list) or not all(
        isinstance(item, dict) and "key" in item and (("secret-id" in item) and len(item) == 2) for item in juju
    ):
        raise ValueError(
            "Invalid secrets structure: 'juju' should be a list of dictionaries with 'key' and 'secret-id'"
        )

    # Validate vault key
    vault = secrets_key.get("vault", [])
    if not isinstance(vault, list) or not all(
        isinstance(item, dict) and "path" in item and "key" in item and len(item) == 2 for item in vault
    ):
        raise ValueError("Invalid secrets structure: 'vault' should be a list of dictionaries with 'path' and 'key'")

    env = secrets_key.get("env", [])
    juju = secrets_key.get("juju", [])
    vault = secrets_key.get("vault", [])

    parsed_data = {
        "env": {list(item.keys())[0]: list(item.values())[0] for item in env},
        "juju": [{"secret-id": item.get("secret-id"), "key": item.get("key")} for item in juju],
        "vault": [{"path": item.get("path"), "key": item.get("key")} for item in vault],
    }

    return parsed_data
