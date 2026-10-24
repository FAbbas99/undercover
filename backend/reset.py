"""Delete the database and seed it again: `uv run -m backend.reset`."""

from backend.db import connect, db_path

if __name__ == "__main__":
    db_path().unlink(missing_ok=True)
    connect().close()
    print(f"Reset {db_path()}")
