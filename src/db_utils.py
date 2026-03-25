from typing import Optional

import requests
from requests.auth import HTTPBasicAuth
from arango import ArangoClient
from arango.exceptions import DatabaseCreateError
from config import (
    ARANGO_ENDPOINT,
    ARANGO_USERNAME,
    ARANGO_PASSWORD,
    ARANGO_DATABASE,
    ARANGO_REPLICATION_FACTOR,
    ARANGO_WRITE_CONCERN,
)

def get_arango_client():
    """Returns an ArangoDB client instance."""
    return ArangoClient(hosts=ARANGO_ENDPOINT)

def get_db():
    """Returns an ArangoDB database instance."""
    client = get_arango_client()
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

def get_system_db():
    """Returns an ArangoDB system database instance."""
    client = get_arango_client()
    return client.db('_system', username=ARANGO_USERNAME, password=ARANGO_PASSWORD)


def create_oneshard_database(
    name: str,
    *,
    replication_factor: Optional[int] = None,
    write_concern: Optional[int] = None,
) -> bool:
    """
    Create a **OneShard** database (``sharding="single"``).

    On an **Enterprise cluster**, all collections in this database are placed on a
    single DB-Server leader (replicas may still live on other DB-Servers when
    ``replication_factor > 1``). On a **single-server** instance, ``sharding`` may be
    ignored; callers can use :func:`create_oneshard_database_or_fallback`.

    Uses :envvar:`ARANGO_REPLICATION_FACTOR` and :envvar:`ARANGO_WRITE_CONCERN` when
    the corresponding arguments are omitted (cluster HA).

    :param name: Database name.
    :param replication_factor: Override replication factor (cluster only).
    :param write_concern: Override write concern (cluster only).
    :return: ``True`` if the database was created.
    :raises DatabaseCreateError: If creation fails (e.g. name taken, permission denied).
    """
    sys_db = get_system_db()
    rf = ARANGO_REPLICATION_FACTOR if replication_factor is None else replication_factor
    wc = ARANGO_WRITE_CONCERN if write_concern is None else write_concern

    kwargs: dict = {"sharding": "single"}
    if rf is not None:
        kwargs["replication_factor"] = rf
    if wc is not None:
        kwargs["write_concern"] = wc

    return bool(sys_db.create_database(name, **kwargs))


def create_oneshard_database_or_fallback(name: str) -> bool:
    """
    Create a OneShard database, or fall back to a plain ``create_database`` if the server
    rejects ``sharding=single`` (e.g. some single-server builds).
    """
    sys_db = get_system_db()
    rf = ARANGO_REPLICATION_FACTOR
    wc = ARANGO_WRITE_CONCERN
    kwargs: dict = {"sharding": "single"}
    if rf is not None:
        kwargs["replication_factor"] = rf
    if wc is not None:
        kwargs["write_concern"] = wc
    try:
        return bool(sys_db.create_database(name, **kwargs))
    except DatabaseCreateError:
        return bool(sys_db.create_database(name))


def get_requests_auth():
    """Returns HTTPBasicAuth for requests."""
    return HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD)

def get_api_url(path=""):
    """Constructs an ArangoDB API URL."""
    base = f"{ARANGO_ENDPOINT}/_db/{ARANGO_DATABASE}/_api"
    if path:
        return f"{base}/{path.lstrip('/')}"
    return base
