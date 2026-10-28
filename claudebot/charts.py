"""Draw charts from a small spec the model fills in, as PNGs for Telegram.

Colors and marks follow a validated categorical palette (fixed slot order, checked for
color-blind separation on this surface) with recessive hairline grids and neutral text. Rendering
is local and deterministic: the model supplies data, never code.
"""

import io
import math
from itertools import pairwise

import matplotlib

matplotlib.use("Agg")
# Labels are plain text: "$" means dollars here, not math markup ("$0-$50" would lose its signs,
# and an unbalanced pair would crash the render).
matplotlib.rcParams["text.parse_math"] = False
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

CHART_TYPES = ("line", "bar", "horizontal_bar", "scatter")
MAX_SERIES = 8
MAX_SCATTER_SERIES = 3  # past three, hues stop being distinguishable for every pair
MAX_POINTS = 500
MAX_BARS = 120  # bars beyond this are unreadable and slow to lay out
MAX_TITLE = 120
MAX_LABEL = 60
DIRECT_LABEL_MAX_SERIES = 4
VALUE_LABEL_MAX_BARS = 15

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

WIDTH_IN, HEIGHT_IN, DPI = 8, 4.5, 160


class ChartError(ValueError):
    pass


def _text(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ChartError(f"Every value must be a finite number, got {value!r}.")
    return float(value)


def validate_spec(spec: dict) -> dict:
    """Check and normalize a chart spec; raise ChartError saying what to fix."""
    kind = spec.get("type")
    if kind not in CHART_TYPES:
        raise ChartError(f"Chart type must be one of {', '.join(CHART_TYPES)} (got {kind!r}). "
                         "For shares of a whole, use a bar chart.")
    raw_series = spec.get("series") or []
    if not raw_series:
        raise ChartError("Give at least one series of values.")
    cap = MAX_SCATTER_SERIES if kind == "scatter" else MAX_SERIES
    if len(raw_series) > cap:
        raise ChartError(f"At most {cap} series for a {kind} chart; fold the smallest into 'Other' "
                         "or make separate charts.")
    series = []
    for item in raw_series:
        values = [_number(v) for v in item.get("values") or []]
        if not values:
            raise ChartError("Every series needs at least one value.")
        if len(values) > MAX_POINTS:
            raise ChartError(f"At most {MAX_POINTS} points per series; aggregate first.")
        series.append({"name": _text(item.get("name"), MAX_LABEL), "values": values})

    length = len(series[0]["values"])
    if any(len(s["values"]) != length for s in series):
        raise ChartError("All series need the same number of values.")
    if kind in ("bar", "horizontal_bar") and length * len(series) > MAX_BARS:
        raise ChartError(f"That's {length * len(series)} bars; at most {MAX_BARS}. Show the top items "
                         "and fold the rest into 'Other', or use a line chart for long time series.")
    categories = [_text(c, MAX_LABEL) for c in spec.get("categories") or []]
    x_values = [_number(x) for x in spec.get("x_values") or []]
    if kind == "scatter":
        if len(x_values) != length:
            raise ChartError("A scatter chart needs x_values with one number per value.")
    elif categories and len(categories) != length:
        raise ChartError(f"categories has {len(categories)} labels but the series have {length} values.")
    elif not categories:
        categories = [str(x) for x in x_values] if len(x_values) == length else [str(i + 1) for i in range(length)]

    return {
        "type": kind,
        "title": _text(spec.get("title"), MAX_TITLE),
        "x_label": _text(spec.get("x_label"), MAX_LABEL),
        "y_label": _text(spec.get("y_label"), MAX_LABEL),
        "categories": categories,
        "x_values": x_values,
        "series": series,
    }


def _compact(value: float, _pos=None) -> str:
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            return f"{value / size:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:g}"


def _style(ax, value_axis: str) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    if value_axis == "x":  # horizontal bars: baseline on the left
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(True)
        ax.spines["left"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelcolor=TEXT_SECONDARY, length=0, labelsize=9)
    ax.grid(axis=value_axis, color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    getattr(ax, f"{value_axis}axis").set_major_formatter(FuncFormatter(_compact))


def _bars(ax, spec: dict, horizontal: bool) -> None:
    series, categories = spec["series"], spec["categories"]
    group = 0.7
    width = min(group / len(series), 0.3)  # thin bars: leave air in each slot
    positions = range(len(categories))
    for i, s in enumerate(series):
        offset = (i - (len(series) - 1) / 2) * width
        where = [p + offset for p in positions]
        draw = ax.barh if horizontal else ax.bar
        bars = draw(where, s["values"], width, color=SERIES[i], label=s["name"],
                    edgecolor=SURFACE, linewidth=1.5)  # surface gap between neighbors
        if len(series) == 1 and len(categories) <= VALUE_LABEL_MAX_BARS:
            ax.bar_label(bars, labels=[_compact(v) for v in s["values"]], padding=3,
                         color=TEXT_SECONDARY, fontsize=9)
    if horizontal:
        ax.set_yticks(list(positions), categories)
        ax.invert_yaxis()  # first category on top, like a ranked list
    else:
        ax.set_xticks(list(positions), categories)
        if len(categories) > 6 or max(len(c) for c in categories) > 8:
            ax.tick_params(axis="x", labelrotation=30)
            for label in ax.get_xticklabels():
                label.set_horizontalalignment("right")


def _lines(ax, spec: dict) -> None:
    categories = spec["categories"]
    positions = list(range(len(categories)))
    show_markers = len(categories) <= 30
    for i, s in enumerate(spec["series"]):
        ax.plot(positions, s["values"], color=SERIES[i], linewidth=2, solid_joinstyle="round",
                solid_capstyle="round", label=s["name"],
                marker="o" if show_markers else None, markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
    if 1 < len(spec["series"]) <= DIRECT_LABEL_MAX_SERIES:
        ends = [s["values"][-1] for s in spec["series"]]
        low, high = ax.get_ylim()
        for name, y in zip((s["name"] for s in spec["series"]), _spread(ends, high - low), strict=True):
            ax.annotate(name, (positions[-1], y), xytext=(8, 0), textcoords="offset points",
                        va="center", color=TEXT_SECONDARY, fontsize=9)
    step = max(1, len(categories) // 10)
    ax.set_xticks(positions[::step], categories[::step])
    ax.margins(x=0.08 if len(spec["series"]) > 1 else 0.03)


def _spread(values: list[float], axis_span: float) -> list[float]:
    """Nudge end-of-line label positions apart so close values don't print on top of each other."""
    gap = (axis_span or 1.0) * 0.05  # about one label height on this figure
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = list(values)
    for prev, cur in pairwise(order):
        placed[cur] = max(placed[cur], placed[prev] + gap)
    return placed


def _scatter(ax, spec: dict) -> None:
    for i, s in enumerate(spec["series"]):
        ax.scatter(spec["x_values"], s["values"], s=48, color=SERIES[i], label=s["name"],
                   edgecolors=SURFACE, linewidths=1.5, zorder=3)
    ax.xaxis.set_major_formatter(FuncFormatter(_compact))


def render_chart(spec: dict) -> bytes:
    """Render a validated spec to PNG bytes. Thread-safe (no pyplot global state)."""
    fig = Figure(figsize=(WIDTH_IN, HEIGHT_IN), dpi=DPI, facecolor=SURFACE)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    kind = spec["type"]
    _style(ax, "x" if kind == "horizontal_bar" else "y")
    if kind in ("bar", "horizontal_bar"):
        _bars(ax, spec, horizontal=kind == "horizontal_bar")
    elif kind == "line":
        _lines(ax, spec)
    else:
        _scatter(ax, spec)
        ax.grid(axis="x", color=GRID, linewidth=0.8)

    title_pad = 30 if len(spec["series"]) > 1 else 14  # room for the legend row above the plot
    ax.set_title(spec["title"], loc="left", color=TEXT_PRIMARY, fontsize=13, pad=title_pad, fontweight="bold")
    ax.set_xlabel(spec["x_label"], color=TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel(spec["y_label"], color=TEXT_SECONDARY, fontsize=9)
    if len(spec["series"]) > 1:  # identity never rides on color alone
        # Above the plot area, under the title: never on top of the data or the grid.
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=min(len(spec["series"]), 4),
                  frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, borderaxespad=0.2,
                  handlelength=1.4)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=SURFACE)
    return buffer.getvalue()
