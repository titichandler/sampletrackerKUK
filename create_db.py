#!/usr/bin/env python3
"""Create the local SQLite database and ORM tables.

Usage (from project root):
    .venv\\Scripts\\python.exe create_db.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sampletracker.db.database import create_database, get_database_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SQLite database tables.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help=f"SQLite file path (default: {get_database_path()})",
    )
    args = parser.parse_args()

    db_path = create_database(args.db_path)
    print(f"Database created: {db_path}")
    print("Tables: formula_library, sample_requests")


if __name__ == "__main__":
    main()
