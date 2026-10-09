"""
Native Canvas Chart Engine for Tkinter
Provides lightweight, zero-dependency charts using standard tk.Canvas:
- Portfolio Allocation Donut / Pie Chart with legend and percentages.
- DRIP Compounding Growth Chart (Principal vs Dividends).
- Performance & Allocation bar gauges.
"""

import math
import tkinter as tk
from typing import List, Dict, Any, Tuple, Optional


class ChartTheme:
    LIGHT = {
        "bg": "#ffffff",
        "fg": "#202124",
        "muted": "#5f6368",
        "grid": "#e8eaed",
        "donut_center": "#ffffff",
        "bar_principal": "#1a73e8",
        "bar_dividend": "#0f9d58",
        "palette": [
            "#1a73e8", "#0f9d58", "#fbbc04", "#ea4335", "#9334e6",
            "#00acc1", "#ff7043", "#3949ab", "#43a047", "#e91e63",
        ]
    }
    
    DARK = {
        "bg": "#1e222d",
        "fg": "#e8eaed",
        "muted": "#9aa0a6",
        "grid": "#2d3342",
        "donut_center": "#1e222d",
        "bar_principal": "#8ab4f8",
        "bar_dividend": "#81c995",
        "palette": [
            "#8ab4f8", "#81c995", "#fdd663", "#f28b82", "#c58af9",
            "#78d9ec", "#ff8a65", "#7986cb", "#a5d6a7", "#f48fb1",
        ]
    }


def draw_donut_chart(
    canvas: tk.Canvas,
    labels: List[str],
    values: List[float],
    title: str = "Portfolio Allocation",
    center_text: str = "",
    dark_mode: bool = False,
) -> None:
    """
    Renders an interactive-style donut chart with a legend on a tk.Canvas.
    """
    canvas.delete("all")
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 50:
        try:
            w = int(canvas.winfo_fpixels(canvas.cget("width")))
        except Exception:
            w = 400
        if w < 50:
            w = 400
    if h < 50:
        try:
            h = int(canvas.winfo_fpixels(canvas.cget("height")))
        except Exception:
            h = 300
        if h < 50:
            h = 300

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    total = sum(values)
    if total <= 0:
        canvas.create_text(
            w / 2, h / 2,
            text="No holdings data to display",
            font=("Segoe UI", 11),
            fill=theme["muted"],
        )
        return

    # Sizing for donut
    margin = 20
    # Left side: Donut chart, Right side: Legend
    legend_w = min(180, w * 0.42)
    chart_cx = (w - legend_w) / 2
    chart_cy = h / 2 + 10
    outer_r = min(chart_cx - margin, (h - margin * 2) / 2) * 0.88
    inner_r = outer_r * 0.55

    # Title
    canvas.create_text(
        margin, 18,
        text=title,
        font=("Segoe UI", 11, "bold"),
        fill=theme["fg"],
        anchor="w",
    )

    # Calculate angles
    colors = theme["palette"]
    start_angle = 90.0

    # Bounding box for outer circle
    x0, y0 = chart_cx - outer_r, chart_cy - outer_r
    x1, y1 = chart_cx + outer_r, chart_cy + outer_r

    # Bounding box for inner hole
    ix0, iy0 = chart_cx - inner_r, chart_cy - inner_r
    ix1, iy1 = chart_cx + inner_r, chart_cy + inner_r

    # Draw slices
    if len(labels) == 1 or any((val / total) >= 0.9999 for val in values):
        # 100% single holding - draw full outer circle (Tkinter arc with extent 360 evaluates to 0)
        canvas.create_oval(
            x0, y0, x1, y1,
            fill=colors[0],
            outline=theme["bg"],
            width=2,
        )
    else:
        for i, (lbl, val) in enumerate(zip(labels, values)):
            extent = (val / total) * 360.0
            if extent <= 0:
                continue
            extent = min(extent, 359.99)
            color = colors[i % len(colors)]

            # Draw outer slice
            canvas.create_arc(
                x0, y0, x1, y1,
                start=start_angle,
                extent=extent,
                fill=color,
                outline=theme["bg"],
                width=2,
            )

            start_angle += extent

    # Draw center hole
    canvas.create_oval(
        ix0, iy0, ix1, iy1,
        fill=theme["donut_center"],
        outline=theme["bg"],
        width=2,
    )

    # Center text
    if center_text:
        canvas.create_text(
            chart_cx, chart_cy - 8,
            text="Total Value",
            font=("Segoe UI", 8),
            fill=theme["muted"],
        )
        canvas.create_text(
            chart_cx, chart_cy + 8,
            text=center_text,
            font=("Segoe UI", 10, "bold"),
            fill=theme["fg"],
        )

    # Draw Legend on the right
    leg_x = w - legend_w + 10
    leg_y = 35
    for i, (lbl, val) in enumerate(zip(labels[:10], values[:10])):
        pct = (val / total) * 100.0
        color = colors[i % len(colors)]

        # Color swatch
        canvas.create_rectangle(
            leg_x, leg_y - 5,
            leg_x + 10, leg_y + 5,
            fill=color,
            outline="",
        )

        # Label and percentage
        display_str = f"{lbl[:10]} ({pct:.1f}%)"
        canvas.create_text(
            leg_x + 16, leg_y,
            text=display_str,
            font=("Segoe UI", 8),
            fill=theme["fg"],
            anchor="w",
        )
        leg_y += 20


def draw_drip_growth_chart(
    canvas: tk.Canvas,
    drip_history: List[Dict[str, Any]],
    dark_mode: bool = False,
) -> None:
    """
    Renders a bar/area chart showing Year-by-Year portfolio compounding from DRIP reinvestment.
    """
    canvas.delete("all")
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 50:
        try:
            w = int(canvas.winfo_fpixels(canvas.cget("width")))
        except Exception:
            w = 560
        if w < 50:
            w = 560
    if h < 50:
        try:
            h = int(canvas.winfo_fpixels(canvas.cget("height")))
        except Exception:
            h = 300
        if h < 50:
            h = 300

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    if not drip_history:
        canvas.create_text(
            w / 2, h / 2,
            text="Run DRIP simulation to view compounding growth chart",
            font=("Segoe UI", 10),
            fill=theme["muted"],
        )
        return

    # Chart padding
    pad_left = 65
    pad_right = 30
    pad_top = 40
    pad_bottom = 40

    plot_w = w - pad_left - pad_right
    plot_h = h - pad_top - pad_bottom

    # Title
    canvas.create_text(
        pad_left, 18,
        text="📊 DRIP Compounding Growth (Invested vs Total Value)",
        font=("Segoe UI", 10, "bold"),
        fill=theme["fg"],
        anchor="w",
    )

    # Max value for y-axis
    max_val = max(row.get("portfolio_value", 0.0) for row in drip_history)
    max_val = max(max_val * 1.15, 1000.0)

    # Draw gridlines and y-axis labels (4 steps)
    for step in range(5):
        y_frac = step / 4.0
        val_at_line = max_val * (1.0 - y_frac)
        y_pos = pad_top + y_frac * plot_h

        # Grid line
        canvas.create_line(
            pad_left, y_pos,
            w - pad_right, y_pos,
            fill=theme["grid"],
            dash=(2, 4),
        )

        # Label
        canvas.create_text(
            pad_left - 8, y_pos,
            text=f"${val_at_line:,.0f}",
            font=("Segoe UI", 7),
            fill=theme["muted"],
            anchor="e",
        )

    # Draw bars for each year
    num_years = len(drip_history)
    bar_group_w = plot_w / num_years
    bar_w = max(4, min(24, bar_group_w * 0.65))

    for i, row in enumerate(drip_history):
        yr = row.get("year", i + 1)
        tot_val = row.get("portfolio_value", 0.0)
        invested = row.get("total_invested", 0.0)
        reinvested_profit = max(0.0, tot_val - invested)

        cx = pad_left + i * bar_group_w + bar_group_w / 2
        bx0 = cx - bar_w / 2
        bx1 = cx + bar_w / 2

        # Base Y position (bottom)
        base_y = pad_top + plot_h

        # Invested height
        h_invested = (invested / max_val) * plot_h
        y_invested = base_y - h_invested

        # Total value height
        h_total = (tot_val / max_val) * plot_h
        y_total = base_y - h_total

        # Draw Reinvested Profit (top part)
        if reinvested_profit > 0 and y_total < y_invested:
            canvas.create_rectangle(
                bx0, y_total,
                bx1, y_invested,
                fill=theme["bar_dividend"],
                outline="",
            )

        # Draw Invested Principal (bottom part)
        canvas.create_rectangle(
            bx0, y_invested,
            bx1, base_y,
            fill=theme["bar_principal"],
            outline="",
        )

        # Year label below
        if num_years <= 15 or yr % 2 == 1:
            canvas.create_text(
                cx, base_y + 12,
                text=f"Y{yr}",
                font=("Segoe UI", 7),
                fill=theme["muted"],
            )

    # Legend at top right
    leg_x = w - pad_right - 170
    leg_y = 18

    # Principal
    canvas.create_rectangle(leg_x, leg_y - 4, leg_x + 10, leg_y + 4, fill=theme["bar_principal"], outline="")
    canvas.create_text(leg_x + 14, leg_y, text="Principal", font=("Segoe UI", 7), fill=theme["muted"], anchor="w")

    # Reinvested Dividends
    canvas.create_rectangle(leg_x + 75, leg_y - 4, leg_x + 85, leg_y + 4, fill=theme["bar_dividend"], outline="")
    canvas.create_text(leg_x + 89, leg_y, text="Reinvested Gains", font=("Segoe UI", 7), fill=theme["muted"], anchor="w")


def draw_fee_tax_trajectory_chart(
    canvas: tk.Canvas,
    trajectory: List[Dict[str, Any]],
    dark_mode: bool = False,
) -> None:
    """
    Renders William J. Bernstein's 30-Year Compounding Wealth Trajectory Chart:
    - Gross Wealth (0% Drag ideal baseline)
    - Benchmark Wealth (0.04% TER low-cost index core)
    - Portfolio Wealth (Actual net compounding with TER, WHT, and CGT drag)
    - Shaded friction loss area between gross and portfolio wealth.
    """
    canvas.delete("all")
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 50:
        try:
            w = int(canvas.winfo_fpixels(canvas.cget("width")))
        except Exception:
            w = 700
        if w < 50:
            w = 700
    if h < 50:
        try:
            h = int(canvas.winfo_fpixels(canvas.cget("height")))
        except Exception:
            h = 220
        if h < 50:
            h = 220

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    if not trajectory:
        canvas.create_text(
            w / 2, h / 2,
            text="No trajectory data available",
            font=("Segoe UI", 10),
            fill=theme["muted"],
        )
        return

    pad_left = 75
    pad_right = 35
    pad_top = 34
    pad_bottom = 26

    plot_w = max(50, w - pad_left - pad_right)
    plot_h = max(50, h - pad_top - pad_bottom)

    max_val = max(
        max(row.get("gross_wealth", 0.0), row.get("benchmark_wealth", 0.0), row.get("portfolio_wealth", 0.0))
        for row in trajectory
    )
    max_val = max(max_val * 1.08, 1000.0)

    # Title
    canvas.create_text(
        pad_left, 16,
        text="📈 30-Year Compounding Trajectory (Gross vs Benchmark vs Actual Portfolio)",
        font=("Segoe UI", 8, "bold"),
        fill=theme["fg"],
        anchor="w",
    )

    # Draw gridlines and Y-axis labels
    for step in range(5):
        y_frac = step / 4.0
        val_at_line = max_val * (1.0 - y_frac)
        y_pos = pad_top + y_frac * plot_h

        # Grid line
        canvas.create_line(
            pad_left, y_pos,
            w - pad_right, y_pos,
            fill=theme["grid"],
            dash=(2, 4),
        )

        # Label formatting (millions or thousands)
        if val_at_line >= 1_000_000:
            lbl_txt = f"${val_at_line / 1_000_000:.1f}M"
        elif val_at_line >= 1_000:
            lbl_txt = f"${val_at_line / 1_000:.0f}K"
        else:
            lbl_txt = f"${val_at_line:,.0f}"

        canvas.create_text(
            pad_left - 8, y_pos,
            text=lbl_txt,
            font=("Segoe UI", 7),
            fill=theme["muted"],
            anchor="e",
        )

    num_pts = len(trajectory)
    if num_pts < 2:
        return

    gross_pts = []
    bench_pts = []
    port_pts = []

    for i, row in enumerate(trajectory):
        yr = row.get("year", i + 1)
        x = pad_left + (i / (num_pts - 1)) * plot_w

        g = row.get("gross_wealth", 0.0)
        b = row.get("benchmark_wealth", 0.0)
        p = row.get("portfolio_wealth", 0.0)

        gy = pad_top + (1.0 - (g / max_val)) * plot_h
        by = pad_top + (1.0 - (b / max_val)) * plot_h
        py = pad_top + (1.0 - (p / max_val)) * plot_h

        gross_pts.append((x, gy))
        bench_pts.append((x, by))
        port_pts.append((x, py))

        # X-axis ticks at key intervals
        if yr in (1, 5, 10, 15, 20, 25, 30):
            canvas.create_line(x, pad_top + plot_h, x, pad_top + plot_h + 3, fill=theme["muted"])
            canvas.create_text(
                x, pad_top + plot_h + 10,
                text=f"Y{yr}",
                font=("Segoe UI", 7),
                fill=theme["muted"],
            )

    # Shaded friction loss polygon between Gross and Portfolio
    fill_poly = []
    for x, y in gross_pts:
        fill_poly.extend([x, y])
    for x, y in reversed(port_pts):
        fill_poly.extend([x, y])

    drag_shade = "#fce8e6" if not dark_mode else "#3c2020"
    if len(fill_poly) >= 6:
        canvas.create_polygon(fill_poly, fill=drag_shade, outline="")

    # Colors
    c_gross = "#0f9d58" if not dark_mode else "#81c995"
    c_bench = "#1a73e8" if not dark_mode else "#8ab4f8"
    c_port = "#d93025" if not dark_mode else "#f28b82"

    # Draw curves
    for pts, col, width in [(gross_pts, c_gross, 2), (bench_pts, c_bench, 2), (port_pts, c_port, 2)]:
        flat = []
        for x, y in pts:
            flat.extend([x, y])
        canvas.create_line(flat, fill=col, width=width, smooth=True)

    # Highlight terminal points at Yr 30
    for pt, col in [(gross_pts[-1], c_gross), (bench_pts[-1], c_bench), (port_pts[-1], c_port)]:
        canvas.create_oval(pt[0] - 3, pt[1] - 3, pt[0] + 3, pt[1] + 3, fill=col, outline="")

    # Legend at top right
    leg_x = max(pad_left + 150, w - pad_right - 350)
    leg_y = 16

    # Gross
    canvas.create_rectangle(leg_x, leg_y - 4, leg_x + 10, leg_y + 4, fill=c_gross, outline="")
    canvas.create_text(leg_x + 14, leg_y, text="Gross (0% Drag)", font=("Segoe UI", 7), fill=theme["muted"], anchor="w")

    # Benchmark
    canvas.create_rectangle(leg_x + 115, leg_y - 4, leg_x + 125, leg_y + 4, fill=c_bench, outline="")
    canvas.create_text(leg_x + 129, leg_y, text="Benchmark (0.04%)", font=("Segoe UI", 7), fill=theme["muted"], anchor="w")

    # Portfolio
    canvas.create_rectangle(leg_x + 245, leg_y - 4, leg_x + 255, leg_y + 4, fill=c_port, outline="")
    canvas.create_text(leg_x + 259, leg_y, text="Actual Portfolio", font=("Segoe UI", 7, "bold"), fill=c_port, anchor="w")


# =============================================================================
# WILLIAM J. BERNSTEIN RETIREMENT & FIRE GRAPHICS ENGINE
# =============================================================================

def _get_canvas_dims(canvas: tk.Canvas, def_w: int = 420, def_h: int = 48) -> Tuple[int, int]:
    """Safely extracts integer width and height from tk.Canvas or test mock."""
    try:
        w_raw = canvas.winfo_width()
        w = int(w_raw) if not isinstance(w_raw, (MagicMock if "MagicMock" in globals() else ())) else 0
    except (ValueError, TypeError, Exception):
        w = 0
    if w < 50:
        try:
            w = int(canvas.winfo_fpixels(canvas.cget("width")))
        except Exception:
            w = def_w
        if w < 50:
            w = def_w

    try:
        h_raw = canvas.winfo_height()
        h = int(h_raw) if not isinstance(h_raw, (MagicMock if "MagicMock" in globals() else ())) else 0
    except (ValueError, TypeError, Exception):
        h = 0
    if h < 20:
        try:
            h = int(canvas.winfo_fpixels(canvas.cget("height")))
        except Exception:
            h = def_h
        if h < 20:
            h = def_h
    return w, h


def draw_fire_asset_ratio_bar(
    canvas: tk.Canvas,
    equity_val: float,
    safe_val: float,
    currency_prefix: str = "$",
    dark_mode: bool = False,
) -> None:
    """
    Renders a 2-segment horizontal asset allocation bar gauge:
    Growth Equity vs. Safe Liability Buffer.
    """
    canvas.delete("all")
    w, h = _get_canvas_dims(canvas, def_w=420, def_h=44)

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    total = max(0.0, equity_val + safe_val)
    margin_x = 10
    bar_y0 = 20
    bar_h = 16
    bar_y1 = bar_y0 + bar_h
    plot_w = max(20, w - (margin_x * 2))

    if total <= 0:
        canvas.create_text(
            w / 2, h / 2,
            text="No asset data available",
            font=("Segoe UI", 8),
            fill=theme["muted"],
        )
        return

    eq_pct = (equity_val / total) * 100.0 if total > 0 else 0.0
    safe_pct = (safe_val / total) * 100.0 if total > 0 else 0.0
    eq_w = max(0.0, min(float(plot_w), float(plot_w) * (equity_val / total)))
    safe_w = float(plot_w) - eq_w

    c_equity = "#1a73e8" if not dark_mode else "#8ab4f8"
    c_safe = "#0f9d58" if not dark_mode else "#81c995"
    track_bg = "#e8eaed" if not dark_mode else "#2d3342"

    # Header labels
    canvas.create_text(
        margin_x, 10,
        text=f"📈 Equity: {currency_prefix}{equity_val:,.0f} ({eq_pct:.1f}%)",
        font=("Segoe UI", 8, "bold"),
        fill=c_equity,
        anchor="w",
    )
    canvas.create_text(
        w - margin_x, 10,
        text=f"🛡️ Safe: {currency_prefix}{safe_val:,.0f} ({safe_pct:.1f}%)",
        font=("Segoe UI", 8, "bold"),
        fill=c_safe,
        anchor="e",
    )

    # Background track
    canvas.create_rectangle(
        margin_x, bar_y0, margin_x + plot_w, bar_y1,
        fill=track_bg, outline="", width=0,
    )

    # Equity bar segment
    if eq_w > 0:
        canvas.create_rectangle(
            margin_x, bar_y0, margin_x + eq_w, bar_y1,
            fill=c_equity, outline="", width=0,
        )

    # Safe bar segment
    if safe_w > 0:
        canvas.create_rectangle(
            margin_x + eq_w, bar_y0, margin_x + plot_w, bar_y1,
            fill=c_safe, outline="", width=0,
        )

    # Dividing separator
    if eq_w > 0 and safe_w > 0:
        canvas.create_line(
            margin_x + eq_w, bar_y0, margin_x + eq_w, bar_y1,
            fill="#ffffff" if not dark_mode else "#1e222d",
            width=2,
        )


def draw_fire_timeline_bar(
    canvas: tk.Canvas,
    cur_age: int,
    ret_age: int,
    life_exp: int,
    dark_mode: bool = False,
) -> None:
    """
    Renders a life cycle timeline from Current Age -> Retirement Age -> Life Horizon.
    """
    canvas.delete("all")
    w, h = _get_canvas_dims(canvas, def_w=420, def_h=48)

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    # Ensure valid ordering
    cur_age = max(18, min(100, int(cur_age)))
    ret_age = max(cur_age, min(105, int(ret_age)))
    life_exp = max(ret_age + 1, min(120, int(life_exp)))

    total_span = max(1, life_exp - cur_age)

    margin_x = 24
    plot_w = max(20, w - (margin_x * 2))
    bar_y0 = 18
    bar_h = 14
    bar_y1 = bar_y0 + bar_h

    yrs_to_ret = max(0, ret_age - cur_age)
    ret_dur = max(0, life_exp - ret_age)

    accum_w = (yrs_to_ret / total_span) * plot_w
    dist_w = plot_w - accum_w

    c_accum = "#1a73e8" if not dark_mode else "#8ab4f8"
    c_dist = "#0f9d58" if not dark_mode else "#81c995"
    track_bg = "#e8eaed" if not dark_mode else "#2d3342"

    # Base track
    canvas.create_rectangle(
        margin_x, bar_y0, margin_x + plot_w, bar_y1,
        fill=track_bg, outline="", width=0,
    )

    # Draw segments
    if accum_w > 0:
        canvas.create_rectangle(
            margin_x, bar_y0, margin_x + accum_w, bar_y1,
            fill=c_accum, outline="", width=0,
        )
    if dist_w > 0:
        canvas.create_rectangle(
            margin_x + accum_w, bar_y0, margin_x + plot_w, bar_y1,
            fill=c_dist, outline="", width=0,
        )

    # Dividing separator
    if accum_w > 0 and dist_w > 0:
        canvas.create_line(
            margin_x + accum_w, bar_y0 - 2, margin_x + accum_w, bar_y1 + 2,
            fill="#ffffff" if not dark_mode else "#1e222d",
            width=2,
        )

    # Markers and Pins
    # Pin 1: Current Age
    canvas.create_text(
        margin_x, 9,
        text=f"● Age {cur_age} (Now)",
        font=("Segoe UI", 7, "bold"),
        fill=theme["fg"],
        anchor="center",
    )

    # Pin 2: Retirement FIRE Age
    ret_x = margin_x + accum_w
    ret_anchor = "center"
    if ret_x < margin_x + 35:
        ret_anchor = "w"
    elif ret_x > margin_x + plot_w - 35:
        ret_anchor = "e"

    canvas.create_text(
        ret_x, 9,
        text=f"★ Age {ret_age} (FIRE)",
        font=("Segoe UI", 7, "bold"),
        fill=c_dist,
        anchor=ret_anchor,
    )

    # Pin 3: Horizon
    canvas.create_text(
        margin_x + plot_w, 9,
        text=f"🏁 Age {life_exp}",
        font=("Segoe UI", 7, "bold"),
        fill=theme["muted"],
        anchor="center",
    )

    # Phase labels under the bar
    if accum_w > 50:
        canvas.create_text(
            margin_x + accum_w / 2, bar_y1 + 8,
            text=f"⏳ {yrs_to_ret}y Accumulation",
            font=("Segoe UI", 7),
            fill=c_accum,
            anchor="center",
        )
    if dist_w > 50:
        canvas.create_text(
            margin_x + accum_w + dist_w / 2, bar_y1 + 8,
            text=f"🏖️ {ret_dur}y Distribution",
            font=("Segoe UI", 7),
            fill=c_dist,
            anchor="center",
        )


def draw_fire_comparison_gauge(
    canvas: tk.Canvas,
    current_val: float,
    target_val: float,
    label_cur: str = "Current",
    label_tgt: str = "Target",
    unit_prefix: str = "$",
    projection_note: str = "",
    dark_mode: bool = False,
) -> None:
    """
    Renders a high-clarity horizontal target vs current comparison gauge bar:
    Shows current progress, gap / surplus, and projection note.
    """
    canvas.delete("all")
    w, h = _get_canvas_dims(canvas, def_w=420, def_h=44)

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    margin_x = 8
    plot_w = max(20, w - (margin_x * 2))
    bar_y0 = 17
    bar_h = 14
    bar_y1 = bar_y0 + bar_h

    track_bg = "#e8eaed" if not dark_mode else "#2d3342"
    c_success = "#0f9d58" if not dark_mode else "#81c995"
    c_blue = "#1a73e8" if not dark_mode else "#8ab4f8"
    c_amber = "#f29900" if not dark_mode else "#fdd663"
    c_red_gap = "#ea4335" if not dark_mode else "#f28b82"

    cov_ratio = (current_val / target_val) if target_val > 0 else (1.0 if current_val >= 0 else 0.0)
    cov_pct = cov_ratio * 100.0

    # Header labels
    cur_text = f"{label_cur}: {unit_prefix}{current_val:,.0f} ({cov_pct:.1f}%)"
    tgt_text = f"{label_tgt}: {unit_prefix}{target_val:,.0f}"

    header_col = c_success if cov_ratio >= 1.0 else (c_amber if cov_ratio >= 0.75 else theme["fg"])
    canvas.create_text(
        margin_x, 8,
        text=cur_text,
        font=("Segoe UI", 8, "bold"),
        fill=header_col,
        anchor="w",
    )
    canvas.create_text(
        w - margin_x, 8,
        text=tgt_text,
        font=("Segoe UI", 7, "bold"),
        fill=theme["muted"],
        anchor="e",
    )

    # Base track
    canvas.create_rectangle(
        margin_x, bar_y0, margin_x + plot_w, bar_y1,
        fill=track_bg, outline="", width=0,
    )

    if target_val <= 0 and current_val <= 0:
        pass
    elif cov_ratio >= 1.0:
        # Met or exceeded target
        canvas.create_rectangle(
            margin_x, bar_y0, margin_x + plot_w, bar_y1,
            fill=c_success, outline="", width=0,
        )
        surplus = current_val - target_val
        surplus_txt = f"✓ Target Met (+{unit_prefix}{surplus:,.0f} Surplus)" if surplus > 0 else "✓ Target Met (100%)"
        canvas.create_text(
            margin_x + plot_w / 2, bar_y0 + bar_h / 2,
            text=surplus_txt,
            font=("Segoe UI", 7, "bold"),
            fill="#ffffff",
            anchor="center",
        )
    else:
        # Partial progress
        fill_w = max(0.0, min(float(plot_w), float(plot_w) * cov_ratio))
        fill_col = c_blue if cov_ratio >= 0.5 else c_amber

        if fill_w > 0:
            canvas.create_rectangle(
                margin_x, bar_y0, margin_x + fill_w, bar_y1,
                fill=fill_col, outline="", width=0,
            )

        # Remaining shortfall segment in shaded red
        gap_val = target_val - current_val
        gap_w = float(plot_w) - fill_w
        gap_bg = "#fce8e6" if not dark_mode else "#3c2020"
        if gap_w > 0:
            canvas.create_rectangle(
                margin_x + fill_w, bar_y0, margin_x + plot_w, bar_y1,
                fill=gap_bg, outline=c_red_gap, width=1,
            )

        # Percentage or gap text inside
        if fill_w > 45:
            canvas.create_text(
                margin_x + fill_w / 2, bar_y0 + bar_h / 2,
                text=f"{cov_pct:.1f}%",
                font=("Segoe UI", 7, "bold"),
                fill="#ffffff",
                anchor="center",
            )
        if gap_w > 65:
            canvas.create_text(
                margin_x + fill_w + gap_w / 2, bar_y0 + bar_h / 2,
                text=f"Gap: -{unit_prefix}{gap_val:,.0f}",
                font=("Segoe UI", 7, "bold"),
                fill=c_red_gap,
                anchor="center",
            )

    # Sub-footer note / projection
    if projection_note:
        canvas.create_text(
            margin_x, bar_y1 + 8,
            text=projection_note,
            font=("Segoe UI", 7),
            fill=theme["muted"],
            anchor="w",
        )


def draw_fire_burn_meter(
    canvas: tk.Canvas,
    burn_rate_pct: float,
    dark_mode: bool = False,
) -> None:
    """
    Renders a 3-zone Bernstein Burn Rate corridor meter:
    - Zone 1: 0.0% ~ 2.0% (Green: Safe & Abundant)
    - Zone 2: 2.0% ~ 3.5% (Yellow: Sustainable Bernstein SWR Corridor)
    - Zone 3: 3.5% ~ 6.0%+ (Red: Fritz Over-Burn Danger)
    With pointer pin and current burn rate label.
    """
    canvas.delete("all")
    w, h = _get_canvas_dims(canvas, def_w=420, def_h=48)

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    margin_x = 20
    plot_w = max(20, w - (margin_x * 2))
    bar_y0 = 18
    bar_h = 12
    bar_y1 = bar_y0 + bar_h

    # Max scale: 6.0%
    max_scale = 6.0
    z1_w = (2.0 / max_scale) * plot_w
    z2_w = (1.5 / max_scale) * plot_w
    z3_w = plot_w - z1_w - z2_w

    c_z1 = "#0f9d58" if not dark_mode else "#81c995"
    c_z2 = "#fbbc04" if not dark_mode else "#fdd663"
    c_z3 = "#ea4335" if not dark_mode else "#f28b82"

    # Draw 3 color zones
    canvas.create_rectangle(margin_x, bar_y0, margin_x + z1_w, bar_y1, fill=c_z1, outline="", width=0)
    canvas.create_rectangle(margin_x + z1_w, bar_y0, margin_x + z1_w + z2_w, bar_y1, fill=c_z2, outline="", width=0)
    canvas.create_rectangle(margin_x + z1_w + z2_w, bar_y0, margin_x + plot_w, bar_y1, fill=c_z3, outline="", width=0)

    # Dividing lines between zones
    canvas.create_line(margin_x + z1_w, bar_y0 - 2, margin_x + z1_w, bar_y1 + 2, fill="#ffffff" if not dark_mode else "#1e222d", width=2)
    canvas.create_line(margin_x + z1_w + z2_w, bar_y0 - 2, margin_x + z1_w + z2_w, bar_y1 + 2, fill="#ffffff" if not dark_mode else "#1e222d", width=2)

    # Zone annotations below bar
    canvas.create_text(margin_x + z1_w / 2, bar_y1 + 8, text="<2.0% Safe", font=("Segoe UI", 7), fill=c_z1, anchor="center")
    canvas.create_text(margin_x + z1_w + z2_w / 2, bar_y1 + 8, text="2.0-3.5% SWR", font=("Segoe UI", 7), fill=c_z2, anchor="center")
    canvas.create_text(margin_x + z1_w + z2_w + z3_w / 2, bar_y1 + 8, text=">3.5% Fritz Warning", font=("Segoe UI", 7), fill=c_z3, anchor="center")

    # Current rate needle pointer
    rate_clamped = max(0.0, min(max_scale, burn_rate_pct))
    needle_x = margin_x + (rate_clamped / max_scale) * plot_w

    if burn_rate_pct < 2.0:
        pin_col = c_z1
        status_txt = "Safe"
    elif burn_rate_pct <= 3.5:
        pin_col = c_z2
        status_txt = "Sustainable"
    else:
        pin_col = c_z3
        status_txt = "Over-Burn"

    # Draw pointer marker (triangle) above the bar
    canvas.create_polygon(
        needle_x, bar_y0 - 1,
        needle_x - 5, bar_y0 - 7,
        needle_x + 5, bar_y0 - 7,
        fill=pin_col, outline=theme["fg"], width=1,
    )

    # Pointer text badge
    anchor = "center"
    if needle_x < margin_x + 40:
        anchor = "w"
    elif needle_x > margin_x + plot_w - 40:
        anchor = "e"

    canvas.create_text(
        needle_x, bar_y0 - 11,
        text=f"Current: {burn_rate_pct:.2f}% ({status_txt})",
        font=("Segoe UI", 7, "bold"),
        fill=pin_col,
        anchor=anchor,
    )


def draw_fire_floor_coverage_bar(
    canvas: tk.Canvas,
    ess_cov_pct: float,
    disc_cov_pct: float,
    dark_mode: bool = False,
) -> None:
    """
    Renders visual coverage of Essential Living Floor vs Discretionary buffer.
    """
    canvas.delete("all")
    w, h = _get_canvas_dims(canvas, def_w=420, def_h=36)

    theme = ChartTheme.DARK if dark_mode else ChartTheme.LIGHT
    canvas.configure(bg=theme["bg"])

    margin_x = 8
    plot_w = max(20, w - (margin_x * 2))
    bar_y0 = 15
    bar_h = 12
    bar_y1 = bar_y0 + bar_h

    track_bg = "#e8eaed" if not dark_mode else "#2d3342"
    c_safe = "#0f9d58" if not dark_mode else "#81c995"
    c_warn = "#ea4335" if not dark_mode else "#f28b82"
    c_blue = "#1a73e8" if not dark_mode else "#8ab4f8"

    # Header label
    ess_col = c_safe if ess_cov_pct >= 100.0 else c_warn
    canvas.create_text(
        margin_x, 7,
        text=f"🔒 Essential Floor: {ess_cov_pct:.1f}% Covered",
        font=("Segoe UI", 7, "bold"),
        fill=ess_col,
        anchor="w",
    )
    canvas.create_text(
        w - margin_x, 7,
        text=f"🎉 Discretionary Buffer: {disc_cov_pct:.1f}%",
        font=("Segoe UI", 7, "bold"),
        fill=c_blue,
        anchor="e",
    )

    # Base track
    canvas.create_rectangle(
        margin_x, bar_y0, margin_x + plot_w, bar_y1,
        fill=track_bg, outline="", width=0,
    )

    # Floor fill up to 100%
    ess_ratio = min(1.0, max(0.0, ess_cov_pct / 100.0))
    fill_w = plot_w * ess_ratio
    if fill_w > 0:
        canvas.create_rectangle(
            margin_x, bar_y0, margin_x + fill_w, bar_y1,
            fill=ess_col, outline="", width=0,
        )
