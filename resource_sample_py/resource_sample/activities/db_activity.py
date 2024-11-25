# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from temporalio import activity
import os
import psycopg2
from psycopg2 import sql
from common.messages import ComposeGreetingInput
from psycopg2.extras import RealDictCursor


@activity.defn(name="database_test")
async def database_test(arg: ComposeGreetingInput) -> str:
    db_config = {
        "dbname": os.getenv("TEMPORAL_DB_NAME"),
        "user": os.getenv("TEMPORAL_DB_USER"),
        "password": os.getenv("TEMPORAL_DB_PASSWORD"),
        "host": os.getenv("TEMPORAL_DB_HOST"),
        "port": os.getenv("TEMPORAL_DB_PORT")
    }
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create test table
    table_name = "test_table"
    create_table_query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            value INTEGER NOT NULL
        )
    """).format(table=sql.Identifier(table_name))
    
    cursor.execute(create_table_query)
    conn.commit()
    
    # Insert sample record
    insert_query = sql.SQL("INSERT INTO {table} (name, value) VALUES (%s, %s) RETURNING id").format(
        table=sql.Identifier(table_name)
    )
    cursor.execute(insert_query, ("hello world", 123))
    inserted_id = cursor.fetchone()["id"]
    conn.commit()
    
    # Read the record back
    select_query = sql.SQL("SELECT * FROM {table} WHERE id = %s").format(
        table=sql.Identifier(table_name)
    )
    cursor.execute(select_query, (inserted_id,))
    record = cursor.fetchone()

    # Close the cursor and connection
    if cursor:
        cursor.close()
    if conn:
        conn.close()

    return record["name"]
