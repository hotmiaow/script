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
