"""Draw the database diagram (ERD): tables, columns, primary and foreign keys.

The drawing is not hand-made: it is generated from the real database by
asking SQLite about its own structure:

    SELECT name FROM sqlite_master WHERE type = 'table'   -> the tables
    PRAGMA table_info(<table>)                           -> columns, types, PK
    PRAGMA foreign_key_list(<table>)                     -> the FK links

So if someone changes schema.sql, the diagram changes too.

Run:   python scripts/draw_erd.py      (or type `diagram` in the assistant)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .charts import (BASELINE, MUTED, SERIES_1, SURFACE, TEXT, TEXT_SECONDARY, ChartError,
                     _load_matplotlib)
from .database import SCHEMA_FILE

HEADER_TEXT = "#ffffff"
PK_COLOR = "#eda100"      # yellow key marker
FK_COLOR = "#6250d6"      # violet link marker


@dataclass
class Column:
    name: str
    type: str
    not_null: bool
    is_pk: bool
    fk: tuple[str, str] | None = None      # (parent table, parent column)
    unique: bool = False                   # UNIQUE -> one-to-one link instead of one-to-many


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)


def read_schema(db_path: Path | str | None = None) -> list[Table]:
    """Read tables and keys from the database (or from schema.sql if there is no file yet)."""
    if db_path is not None and Path(db_path).exists():
        connection = sqlite3.connect(str(db_path))
    else:
        connection = sqlite3.connect(":memory:")
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    try:
        names = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name != 'history' ORDER BY rowid")]
        tables = []
        for name in names:
            fks = {row[3]: (row[2], row[4]) for row in
                   connection.execute(f"PRAGMA foreign_key_list('{name}')")}
            unique_cols = set()
            for index in connection.execute(f"PRAGMA index_list('{name}')").fetchall():
                if index[2]:                                   # unique index
                    cols = [r[2] for r in connection.execute(f"PRAGMA index_info('{index[1]}')")]
                    if len(cols) == 1:
                        unique_cols.add(cols[0])
            table = Table(name)
            for _cid, col, col_type, not_null, _default, pk in connection.execute(f"PRAGMA table_info('{name}')"):
                table.columns.append(Column(col, col_type or "", bool(not_null), bool(pk), fks.get(col),
                                            col in unique_cols))
            tables.append(table)
    finally:
        connection.close()
    if not tables:
        raise ChartError("The database has no tables.")
    return tables


def _levels(tables: list[Table]) -> dict[str, int]:
    """Parents on the left, children on the right (column = length of the FK chain)."""
    by_name = {t.name: t for t in tables}
    level: dict[str, int] = {}

    def depth(name: str, seen: frozenset = frozenset()) -> int:
        if name in level:
            return level[name]
        parents = [c.fk[0] for c in by_name[name].columns if c.fk and c.fk[0] in by_name and c.fk[0] not in seen]
        level[name] = 0 if not parents else 1 + max(depth(p, seen | {name}) for p in parents)
        return level[name]

    for t in tables:
        depth(t.name)
    return level


def draw_erd(db_path: Path | str | None, out_file: Path | str) -> Path:
    plt = _load_matplotlib()
    from matplotlib.patches import FancyBboxPatch

    tables = read_schema(db_path)
    level = _levels(tables)
    row_h, header_h, box_w, gap_x = 0.42, 0.55, 4.4, 1.6
    columns_at_level: dict[int, float] = {}

    # Position every table: x from its level, y stacked when several share a level.
    positions: dict[str, tuple[float, float]] = {}
    for t in tables:
        lv = level[t.name]
        top = columns_at_level.get(lv, 0.0)
        positions[t.name] = (lv * (box_w + gap_x), -top)
        columns_at_level[lv] = top + header_h + row_h * len(t.columns) + 1.0

    width = (max(level.values()) + 1) * (box_w + gap_x)
    height = max(columns_at_level.values()) + 1.2
    fig, ax = plt.subplots(figsize=(max(10, width * 1.05), max(5, height * 1.05)))
    ax.set_xlim(-0.3, width - gap_x + 0.3)
    ax.set_ylim(-height + 0.4, 1.2)
    ax.set_axis_off()

    row_y: dict[tuple[str, str], float] = {}
    for t in tables:
        x, y = positions[t.name]
        body_h = row_h * len(t.columns)
        ax.add_patch(FancyBboxPatch((x, y - header_h - body_h), box_w, header_h + body_h,
                                    boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=SURFACE, edgecolor=BASELINE, linewidth=1.2))
        ax.add_patch(FancyBboxPatch((x, y - header_h), box_w, header_h,
                                    boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=SERIES_1, edgecolor=SERIES_1))
        ax.text(x + 0.2, y - header_h / 2, t.name, color=HEADER_TEXT, fontsize=12,
                fontweight="bold", va="center")
        for i, col in enumerate(t.columns):
            cy = y - header_h - row_h * (i + 0.5)
            row_y[(t.name, col.name)] = cy
            if col.is_pk:
                ax.text(x + 0.15, cy, "PK", color=PK_COLOR, fontsize=8.5, fontweight="bold", va="center")
            elif col.fk:
                ax.text(x + 0.15, cy, "FK", color=FK_COLOR, fontsize=8.5, fontweight="bold", va="center")
            ax.text(x + 0.65, cy, col.name, color=TEXT, fontsize=9.5, va="center",
                    fontweight="bold" if col.is_pk else "normal")
            ax.text(x + box_w - 0.15, cy, col.type + ("" if col.not_null or col.is_pk else "  null"),
                    color=MUTED, fontsize=8, va="center", ha="right")
            if i < len(t.columns) - 1:
                ax.plot([x + 0.1, x + box_w - 0.1], [cy - row_h / 2] * 2, color="#ecebe5", linewidth=0.6)

    # Foreign key arrows: child column (N) -> parent primary key (1).
    for t in tables:
        cx, _ = positions[t.name]
        for col in t.columns:
            if not col.fk or col.fk[0] not in positions:
                continue
            parent, parent_col = col.fk
            px, _ = positions[parent]
            start = (cx, row_y[(t.name, col.name)])
            end = (px + box_w, row_y[(parent, parent_col)])
            ax.annotate("", xy=end, xytext=start,
                        arrowprops=dict(arrowstyle="-|>", color=FK_COLOR, linewidth=1.6,
                                        connectionstyle="arc3,rad=0.0", shrinkA=2, shrinkB=2))
            ax.text(start[0] - 0.18, start[1] + 0.14, "0..1" if col.unique else "N", color=FK_COLOR, fontsize=9,
                    fontweight="bold", ha="right")
            ax.text(end[0] + 0.12, end[1] + 0.14, "1", color=FK_COLOR, fontsize=9, fontweight="bold")

    ax.text(-0.25, 1.0, "Database diagram (ERD): assistant.db", fontsize=14, fontweight="bold", color=TEXT)
    ax.text(-0.25, 0.6, "PK = primary key   FK = foreign key   arrow = FOREIGN KEY ... REFERENCES "
            "(N rows point to 1 row; 0..1 = UNIQUE, one-to-one)", fontsize=9, color=TEXT_SECONDARY)

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return out_file
