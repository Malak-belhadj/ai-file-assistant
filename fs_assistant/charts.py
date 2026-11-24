"""Draw the SQL query results from the history database as charts.

Each chart runs ONE SQL query on assistant.db and draws its result. The
query text is printed under the chart, so you can see which query produced
which picture. The charts are saved as PNG images in the `charts/` folder.
Open them in VS Code (click the file) or in any image viewer.

Run:   python scripts/draw_charts.py
or type `charts` inside the assistant.

Needs the `matplotlib` package (pip install -r requirements-dev.txt).
"""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

# Colors (one consistent, colorblind-checked palette)
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES_1 = "#2a78d6"          # blue: the main data color
STATUS_GOOD = "#0ca30c"       # green: succeeded
STATUS_CRITICAL = "#d03b3b"   # red: failed or cancelled

# The queries that are drawn (the same ones as in queries.sql).
QUERIES = {
    "actions": """SELECT action_type, COUNT(*) AS times
FROM actions
GROUP BY action_type
ORDER BY times DESC;""",
    "success": """SELECT SUM(success) AS succeeded,
       COUNT(*) - SUM(success) AS failed
FROM actions;""",
    "speed": """SELECT action_type, ROUND(AVG(duration_ms)) AS avg_ms
FROM actions
WHERE duration_ms IS NOT NULL
GROUP BY action_type
ORDER BY avg_ms DESC;""",
    "per_chat": """SELECT c.conversation_id, c.title, COUNT(m.message_id) AS messages
FROM conversations c
JOIN messages m ON m.conversation_id = c.conversation_id
GROUP BY c.conversation_id
ORDER BY messages DESC
LIMIT 8;""",
}


class ChartError(Exception):
    """A friendly message: missing database, empty history, missing matplotlib."""


def _load_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")                 # draw to files, no window needed
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ChartError("Charts need the 'matplotlib' package. Install it with:  "
                         "pip install -r requirements-dev.txt") from exc
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE, "axes.labelcolor": TEXT_SECONDARY,
        "xtick.color": TEXT_SECONDARY, "ytick.color": TEXT_SECONDARY,
        "text.color": TEXT, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    return plt


def run_queries(db_path: Path | str) -> dict[str, list[tuple]]:
    """Run every chart query and return the rows (also used by the tests)."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise ChartError(f"No database found at '{db_path}'. Run 'python main.py' "
                         "and make a few requests first.")
    connection = sqlite3.connect(str(db_path))
    try:
        results = {name: connection.execute(sql).fetchall() for name, sql in QUERIES.items()}
    except sqlite3.Error as exc:
        raise ChartError(f"Could not read the history database: {exc}") from exc
    finally:
        connection.close()
    total = sum(n for _action, n in results["actions"])
    if total == 0:
        raise ChartError("The history is empty. Make a few requests in the assistant first.")
    return results


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------
def _show_query(fig, sql: str) -> None:
    """Print the SQL query under the chart in a monospace font."""
    fig.text(0.02, 0.02, "SQL:\n" + sql, family="monospace", fontsize=8,
             color=TEXT_SECONDARY, va="bottom", ha="left")


def _style_value_axis(ax, axis: str) -> None:
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _horizontal_bars(ax, labels, values, color, value_format="{:g}") -> None:
    positions = range(len(labels))
    bars = ax.barh(list(positions), values, color=color, height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()                        # biggest at the top
    _style_value_axis(ax, "x")
    ax.spines["left"].set_visible(False)
    top = max(values) if values else 1
    ax.set_xlim(0, top * 1.18)
    for bar, value in zip(bars, values):     # direct labels: the number at the end of each bar
        ax.text(bar.get_width() + top * 0.02, bar.get_y() + bar.get_height() / 2,
                value_format.format(value), va="center", color=TEXT, fontsize=9)


def _draw_actions(ax, rows) -> None:
    labels = [action for action, _n in rows]
    values = [n for _action, n in rows]
    _horizontal_bars(ax, labels, values, SERIES_1)
    ax.set_title("Requests per action", loc="left", fontweight="bold")
    ax.set_xlabel("Number of requests")


def _draw_success(ax, rows) -> None:
    succeeded, failed = rows[0]
    succeeded, failed = int(succeeded or 0), int(failed or 0)
    total = succeeded + failed
    labels = ["Succeeded", "Failed or cancelled"]
    values = [succeeded, failed]
    bars = ax.bar(labels, values, color=[STATUS_GOOD, STATUS_CRITICAL], width=0.55,
                  edgecolor=SURFACE, linewidth=2)
    _style_value_axis(ax, "y")
    ax.spines["left"].set_visible(False)
    top = max(values) if max(values) else 1
    ax.set_ylim(0, top * 1.25)
    for bar, value in zip(bars, values):
        pct = 100 * value / total if total else 0
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top * 0.03,
                f"{value}  ({pct:.0f}%)", ha="center", color=TEXT, fontsize=9)
    rate = 100 * succeeded / total if total else 0
    ax.set_title(f"Success rate: {rate:.0f}%", loc="left", fontweight="bold")
    ax.set_ylabel("Number of requests")


def _draw_speed(ax, rows) -> None:
    if not rows:
        ax.text(0.5, 0.5, "No timing data yet", ha="center", va="center", color=MUTED)
        ax.set_axis_off()
        return
    labels = [action for action, _ms in rows]
    seconds = [(ms or 0) / 1000 for _action, ms in rows]
    _horizontal_bars(ax, labels, seconds, SERIES_1, value_format="{:.1f} s")
    ax.set_title("Average response time per action (AI + disk)", loc="left", fontweight="bold")
    ax.set_xlabel("Seconds")


def _draw_per_chat(ax, rows) -> None:
    if not rows:
        ax.text(0.5, 0.5, "No chats yet", ha="center", va="center", color=MUTED)
        ax.set_axis_off()
        return
    labels = [f"[{cid}] {title[:28] + '...' if len(title) > 31 else title}" for cid, title, _n in rows]
    values = [n for _cid, _title, n in rows]
    _horizontal_bars(ax, labels, values, SERIES_1)
    ax.set_title("Messages per chat (conversations JOIN messages)", loc="left", fontweight="bold")
    ax.set_xlabel("Number of messages")


DRAWERS = {
    "actions": _draw_actions,
    "success": _draw_success,
    "speed": _draw_speed,
    "per_chat": _draw_per_chat,
}

FILE_NAMES = {
    "actions": "1_requests_per_action.png",
    "success": "2_success_rate.png",
    "speed": "3_response_time.png",
    "per_chat": "4_messages_per_chat.png",
}


def draw_all(db_path: Path | str, out_dir: Path | str = "charts") -> list[Path]:
    """Run the queries, draw one PNG per query plus a combined dashboard.

    Returns the list of image files created.
    """
    plt = _load_matplotlib()
    results = run_queries(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # One image per query, with the SQL printed underneath.
    for name, drawer in DRAWERS.items():
        sql = QUERIES[name]
        query_lines = sql.count("\n") + 2
        fig = plt.figure(figsize=(8, 4.2 + 0.18 * query_lines))
        bottom = (0.18 * query_lines + 0.35) / fig.get_figheight()
        ax = fig.add_axes([0.2, bottom + 0.08, 0.72, 0.82 - bottom])
        drawer(ax, results[name])
        _show_query(fig, sql)
        path = out_dir / FILE_NAMES[name]
        fig.savefig(path, dpi=130)
        plt.close(fig)
        created.append(path)

    # All four charts on one page, for the presentation.
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (name, drawer) in zip(axes.flat, DRAWERS.items()):
        drawer(ax, results[name])
    fig.suptitle("AI File System Assistant: database queries (assistant.db)",
                 x=0.02, ha="left", fontsize=13, fontweight="bold")
    fig.text(0.02, 0.005, textwrap.fill("Each chart is the result of one SQL query from queries.sql "
                                        "run on the tables actions, conversations and messages.", 140),
             color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    path = out_dir / "dashboard.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    created.append(path)
    return created
