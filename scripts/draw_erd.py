"""Draw the database diagram (tables, primary keys, foreign keys) as a PNG.

Run from the project folder:
    python scripts/draw_erd.py
Then open charts/database_diagram.png in VS Code.
Works even before the first chat: it then reads fs_assistant/schema.sql.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fs_assistant.erd import ChartError, draw_erd, read_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Draw the database diagram")
    parser.add_argument("--db", default="assistant.db", help="SQLite database file")
    parser.add_argument("--out", default="charts/database_diagram.png", help="output image")
    args = parser.parse_args()
    try:
        tables = read_schema(args.db)
        path = draw_erd(args.db, args.out)
    except ChartError as exc:
        print(f"Error: {exc}")
        return 1
    for table in tables:
        print(f"\nTABLE {table.name}")
        for col in table.columns:
            key = "PK" if col.is_pk else ("FK" if col.fk else "  ")
            link = f"  -> REFERENCES {col.fk[0]}({col.fk[1]})" if col.fk else ""
            print(f"  {key} {col.name:<18} {col.type}{link}")
    print(f"\nDiagram saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
