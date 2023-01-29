import argparse
import configparser
import os
from typing import Any, Optional, Sequence, Tuple

import psycopg2
from psycopg2.extras import execute_values

COMMANDS = ["init", "reset", "destroy"]


def get_db(
    conf: configparser.ConfigParser, superuser: Optional[bool] = False
) -> psycopg2.extensions.connection:
    cfg_section = "ingest" if superuser else "postgresql"
    dbname = conf[cfg_section]["database"]
    user = conf[cfg_section]["user"]
    password = conf[cfg_section].get("password", None)
    host = conf[cfg_section]["host"]
    port = conf[cfg_section]["port"]
    conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
    return conn


def clear_db(conf: configparser.ConfigParser) -> None:
    sql = """
        DROP SCHEMA IF EXISTS mars CASCADE;
        DROP USER IF EXISTS mars_user;
    """
    conn = None
    try:
        conn = get_db(conf, superuser=True)
        cur = conn.cursor()
        cur.execute(sql)
        cur.close()
        conn.commit()
    except psycopg2.DatabaseError as error:
        print("error:", error)
    finally:
        if conn is not None:
            conn.close()


def init_db(conf: configparser.ConfigParser, schema_path: str) -> None:
    conn = None
    try:
        conn = get_db(conf, superuser=True)
        cur = conn.cursor()

        with open(schema_path, "r") as sql:
            cur.execute(sql.read(), (conf["postgresql"]["password"],))

        cur.close()
        conn.commit()
    except psycopg2.DatabaseError as error:
        print("error:", error)
    finally:
        if conn is not None:
            conn.close()


def insert_many(
    conf: configparser.ConfigParser, insert_sql: str, data: Sequence[Tuple[Any, ...]]
) -> None:
    conn = None
    try:
        conn = get_db(conf, superuser=True)
        cur = conn.cursor()
        execute_values(cur, insert_sql, data, page_size=1000)
        cur.close()
        conn.commit()
    except psycopg2.DatabaseError as error:
        print("error: ", error)
    finally:
        if conn is not None:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    this_file_path = os.path.dirname(os.path.realpath(__file__))
    schema_file = "schema.sql"
    schema_full_path = os.path.join(this_file_path, schema_file)

    if args.command == "init":
        init_db(config, schema_full_path)
    elif args.command == "reset":
        clear_db(config)
        init_db(config, schema_full_path)
    elif args.command == "destroy":
        clear_db(config)


if __name__ == "__main__":
    main()
