# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from typing import Optional

import psycopg2
from common.messages import ComposeGreetingInput
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from temporalio import activity


class DBConfig(BaseSettings):
    host: Optional[str] = None
    dbname: Optional[str] = Field(None, alias="TEMPORAL_DB_NAME")
    user: Optional[str] = None
    password: Optional[str] = None
    port: Optional[str] = None

    model_config = SettingsConfigDict(
        env_prefix="TEMPORAL_DB_", case_sensitive=False, populate_by_name=True
    )


@activity.defn(name="database_test")
async def database_test(arg: ComposeGreetingInput) -> str:
    db_config = DBConfig()
    table_name = "test_table"

    with psycopg2.connect(**db_config.model_dump()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:

            # Create test table
            create_table_query = sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    value INTEGER NOT NULL
                )
            """
            ).format(table=sql.Identifier(table_name))
            cursor.execute(create_table_query)
            conn.commit()

            # Insert sample record
            insert_query = sql.SQL(
                "INSERT INTO {table} (name, value) VALUES (%s, %s) RETURNING id"
            ).format(table=sql.Identifier(table_name))
            cursor.execute(insert_query, ("hello world", 123))
            inserted_id = cursor.fetchone()["id"]
            conn.commit()

            # Read the record back
            select_query = sql.SQL("SELECT * FROM {table} WHERE id = %s").format(
                table=sql.Identifier(table_name)
            )
            cursor.execute(select_query, (inserted_id,))
            record = cursor.fetchone()

    return record["name"]
