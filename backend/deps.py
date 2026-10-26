"""What the backend's operations share."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from typing import Annotated

from fastapi import Depends, HTTPException

from backend.db import connect


def database() -> Iterator[sqlite3.Connection]:
    """Open a database connection for one request."""
    with closing(connect()) as conn:
        yield conn


Db = Annotated[sqlite3.Connection, Depends(database)]


def require(condition: bool, message: str) -> None:
    """Refuse the request with 409 unless the condition holds."""
    if not condition:
        raise HTTPException(409, message)
