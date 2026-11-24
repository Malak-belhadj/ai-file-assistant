"""Draw the history database queries as charts (PNG images).

Run from the project folder:
    python scripts/draw_charts.py
    python scripts/draw_charts.py --db assistant.db --out charts

Then open the `charts` folder in VS Code and click an image to view it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fs_assistant.charts import QUERIES, ChartError, draw_all, run_queries  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Draw charts from assistant.db")
    parser.add_argument("--db", default="assistant.db", help="SQLite history file")
    parser.add_argument("--out", default="charts", help="folder for the PNG images")
    args = parser.parse_args()

    try:
        results = run_queries(args.db)
        files = draw_all(args.db, args.out)
    except ChartError as exc:
        print(f"Error: {exc}")
        return 1

    # Also print each query and its result as a table in the terminal.
    for name, sql in QUERIES.items():
        print("\n" + sql)
        for row in results[name]:
            print("   ", " | ".join("" if v is None else str(v) for v in row))

    print("\nCharts created:")
    for path in files:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
