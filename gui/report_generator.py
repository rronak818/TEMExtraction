# -*- coding: utf-8 -*-
"""Generate a research-paper-style PDF from saved TEMExtraction results.

Compatible with the project's legacy Python 3.6 environment.
Does not rerun analysis or modify measurement data.
"""

from __future__ import print_function

import json
import math
import os
import textwrap
from collections import defaultdict
from datetime import datetime

import matplotlib as mpl
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PIL import Image

try:
    from .offline_narrative import generate_narrative
except (ImportError, ValueError):
    from offline_narrative import generate_narrative


MEASUREMENTS = [
    ("rod", "length", "Rod length"),
    ("rod", "width", "Rod width"),
    ("sphere", "diameter", "Sphere diameter"),
    ("triangle", "height", "Triangle height"),
    ("cube", "side", "Cube side"),
]

OBJECT_COUNT_KEYS = [
    ("rod", "length", "Rods"),
    ("sphere", "diameter", "Spheres"),
    ("triangle", "height", "Triangles"),
    ("cube", "side", "Cubes"),
]

PAGE_SIZE = (8.27, 11.69)


def _valid_unit(raw_unit):
    if not isinstance(raw_unit, str):
        return "Unknown units"
    unit = raw_unit.strip()
    if not unit or unit.lower() in (
        "none", "nan", "unknown", "n/a"
    ):
        return "Unknown units"
    return unit


def _finite_number(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _get_values(image_data, group, key):
    if not isinstance(image_data, dict):
        return []
    sizes = image_data.get("Size", {})
    if not isinstance(sizes, dict):
        return []
    group_data = sizes.get(group, {})
    if not isinstance(group_data, dict):
        return []
    raw_values = group_data.get(key, [])
    if not isinstance(raw_values, (list, tuple)):
        return []
    return [
        number for number in (_finite_number(v) for v in raw_values)
        if number is not None
    ]


def _summary_stats(values):
    values = sorted(values)
    count = len(values)
    if not count:
        return None
    mean = sum(values) / float(count)
    median = (
        values[count // 2]
        if count % 2
        else (values[count // 2 - 1] + values[count // 2]) / 2.0
    )
    if count > 1:
        variance = sum((v - mean) ** 2 for v in values) / float(count - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = None
    return {
        "count": count,
        "mean": mean,
        "median": median,
        "std": std_dev,
        "min": values[0],
        "max": values[-1],
    }


def _fill_table_vertical(table, data_row_count, fill_fraction=0.94):
    """Apply one consistent compact row height to every report table."""
    row_height = 0.028

    for (_row_index, _column_index), cell in table.get_celld().items():
        cell.set_height(row_height)
        cell.PAD = 0.015



def _table_page_capacity(max_rows, row_height=0.028,
                         usable_height=0.76, header_rows=1):
    """Return a conservative number of table data rows per A4 page."""
    if max_rows <= 0:
        return 0
    available_rows = int(usable_height / row_height) - header_rows
    return max(1, min(max_rows, available_rows))


def _add_table(fig, rows, headers, bounds, fontsize=7,
               cell_loc="center", col_loc="center", col_widths=None):
    """Add a consistently styled table inside explicit figure bounds."""
    table_ax = fig.add_axes(bounds)
    table_ax.axis("off")
    kwargs = {
        "cellText": rows,
        "colLabels": headers,
        "cellLoc": cell_loc,
        "colLoc": col_loc,
        "loc": "upper center",
    }
    if col_widths is not None:
        kwargs["colWidths"] = col_widths
    table = table_ax.table(**kwargs)
    _style_table(table)
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    _fill_table_vertical(table, len(rows))
    return table

def _style_table(table):
    """Apply restrained serif typography and subtle scientific table styling."""
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#B8B8B8")
        cell.set_linewidth(0.35)
        cell.get_text().set_fontfamily("serif")
        if row == 0:
            cell.set_facecolor("#E8E8E8")
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor("#F7F7F7" if row % 2 else "#FFFFFF")

def _new_page(title, subtitle=None):
    fig = Figure(figsize=PAGE_SIZE, facecolor="white")
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(
        0.08, 0.965, title, transform=ax.transAxes,
        fontsize=14, fontweight="bold", fontfamily="serif",
        color="#202020", va="top", wrap=True
    )
    ax.plot(
        [0.08, 0.92], [0.935, 0.935],
        transform=ax.transAxes, color="#888888",
        linewidth=0.6, clip_on=False
    )
    if subtitle:
        ax.text(
            0.08, 0.915, subtitle, transform=ax.transAxes,
            fontsize=8, fontfamily="serif",
            color="#666666", va="top", wrap=True
        )
    return fig, ax


def _write_text_page(pdf, title, lines, subtitle=None):
    fig, ax = _new_page(title, subtitle)
    y = 0.875
    for line in lines:
        if y < 0.055:
            pdf.savefig(fig, bbox_inches="tight")
            fig, ax = _new_page(title + " (continued)")
            y = 0.91
        wrapped = textwrap.wrap(str(line), width=94) or [""]
        for piece in wrapped:
            ax.text(
                0.05, y, piece, transform=ax.transAxes,
                fontsize=9, va="top"
            )
            y -= 0.027
        y -= 0.008
    pdf.savefig(fig, bbox_inches="tight")



def _write_manuscript(pdf, narrative, run_id, image_count,
                      total_objects, timestamp, manifest, settings):
    """Write a consistently spaced, two-column scientific-style report."""
    import textwrap

    page_title = "TEMExtraction Microscopy Analysis"
    fig = None
    ax = None
    page_number = 0
    column = 0
    y = 0.0
    body_top = 0.0

    left_x = 0.075
    right_x = 0.535
    bottom_y = 0.075
    column_width = 0.39
    line_height = 0.019
    body_font = 8.0

    def begin_page(first=False):
        nonlocal fig, ax, page_number, column, y, body_top
        fig = Figure(figsize=PAGE_SIZE, facecolor="white")
        ax = fig.add_subplot(111)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        page_number += 1
        column = 0

        if first:
            ax.text(
                0.5, 0.965, page_title,
                ha="center", va="top", fontsize=16,
                fontweight="bold", transform=ax.transAxes
            )
            ax.text(
                0.5, 0.929,
                "Microscopy measurements and descriptive analysis",
                ha="center", va="top", fontsize=9.5,
                transform=ax.transAxes
            )
            ax.text(
                0.5, 0.901,
                "Run: {}  |  Images: {}  |  Measured objects: {}".format(
                    run_id, image_count, total_objects
                ),
                ha="center", va="top", fontsize=7.5,
                color="#444444", transform=ax.transAxes
            )
            ax.text(
                0.5, 0.881, "Generated: {}".format(timestamp),
                ha="center", va="top", fontsize=7.5,
                color="#444444", transform=ax.transAxes
            )
            y = 0.845
            body_top = y
        else:
            ax.text(
                left_x, 0.965, page_title,
                ha="left", va="top", fontsize=7.5,
                color="#555555", transform=ax.transAxes
            )
            ax.text(
                1.0 - left_x, 0.965, "Page {}".format(page_number),
                ha="right", va="top", fontsize=7.5,
                color="#555555", transform=ax.transAxes
            )
            ax.plot(
                [left_x, 1.0 - left_x], [0.945, 0.945],
                color="#999999", linewidth=0.45,
                transform=ax.transAxes
            )
            y = 0.915
            body_top = y

    def save_page():
        if fig is None:
            return
        ax.text(
            0.5, 0.027, str(page_number),
            ha="center", va="bottom", fontsize=7,
            color="#555555", transform=ax.transAxes
        )
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        pdf.savefig(fig)

    def next_column():
        nonlocal column, y
        if column == 0:
            column = 1
            y = body_top
        else:
            save_page()
            begin_page(False)

    def ensure_space(height):
        nonlocal y
        if y - height < bottom_y:
            next_column()

    def add_heading(text):
        nonlocal y
        ensure_space(0.045)
        x = left_x if column == 0 else right_x
        ax.text(
            x, y, text, ha="left", va="top",
            fontsize=9.5, fontweight="bold",
            transform=ax.transAxes
        )
        y -= 0.031

    def add_paragraph(text, full_width=False):
        nonlocal y
        if full_width:
            x = left_x
            width = 110
            height = 0.0165
            font_size = 8.0
        else:
            x = left_x if column == 0 else right_x
            width = 54
            height = line_height
            font_size = body_font

        paragraphs = str(text).splitlines() or [""]
        lines = []
        for paragraph in paragraphs:
            lines.extend(textwrap.wrap(
                paragraph, width=width,
                break_long_words=False,
                break_on_hyphens=False
            ) or [""])

        for line in lines:
            ensure_space(height)
            # Recalculate the x-coordinate after any column/page transition.
            if not full_width:
                x = left_x if column == 0 else right_x
            ax.text(
                x, y, line, ha="left", va="top",
                fontsize=font_size, transform=ax.transAxes
            )
            y -= height
        y -= 0.004

    begin_page(True)

    # Abstract spans the page width above the two-column article body.
    add_heading("Abstract")
    for paragraph in narrative.get("abstract", []):
        add_paragraph(paragraph, full_width=True)

    add_paragraph(
        "Keywords: transmission electron microscopy; image analysis; "
        "particle morphology; dimensional measurements",
        full_width=True
    )

    # Start both columns at the same vertical position below the abstract.
    body_top = y - 0.012
    y = body_top

    sections = [
        ("1. Materials and Methods", "methods"),
        ("2. Results", "results"),
        ("3. Discussion", "discussion"),
        ("4. Conclusion", "conclusion"),
        ("5. Limitations", "limitations"),
    ]

    for title, key in sections:
        add_heading(title)
        for paragraph in narrative.get(key, []):
            add_paragraph(paragraph)

    metadata = [
        "Input mode: {}".format(manifest.get("input_mode", "Not recorded")),
        "Run status: {}".format(manifest.get("status", "Not recorded")),
        "Publisher: {}".format(settings.get("publisher", "Not recorded")),
        "DOI: {}".format(settings.get("doi") or "Not recorded"),
        "Year: {}".format(settings.get("year") or "Not recorded"),
        "GPU enabled: {}".format(settings.get("gpu_enabled", "Not recorded")),
    ]
    add_heading("Run metadata")
    for item in metadata:
        add_paragraph(item)

    save_page()

def generate_pdf_report(output_dir, output_path):
    """Generate a complete multi-page report from a saved run directory."""
    sizes_path = os.path.join(output_dir, "sizes.json")
    if not os.path.isfile(sizes_path):
        raise ValueError("The selected output folder has no sizes.json file.")

    with open(sizes_path, "r") as source:
        data = json.load(source)
    if not isinstance(data, dict) or not data:
        raise ValueError("sizes.json contains no usable image results.")

    manifest_path = os.path.join(output_dir, "run_manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r") as source:
                loaded_manifest = json.load(source)
            if isinstance(loaded_manifest, dict):
                manifest = loaded_manifest
        except (OSError, ValueError):
            manifest = {}

    image_count = len(data)
    image_counts = {}
    grouped_values = defaultdict(list)
    detail_rows = []
    total_objects = 0
    invalid_values = 0
    unit_names = set()
    missing_unit_images = []

    for image_name, image_data in data.items():
        unit = _valid_unit(
            image_data.get("Unit") if isinstance(image_data, dict) else None
        )
        if unit == "Unknown units":
            missing_unit_images.append(str(image_name))
        else:
            unit_names.add(unit)

        counts = {}
        for group, key, label in OBJECT_COUNT_KEYS:
            values = _get_values(image_data, group, key)
            counts[label] = len(values)
            total_objects += len(values)

        image_counts[str(image_name)] = {
            "unit": unit,
            "counts": counts,
        }

        for group, key, label in MEASUREMENTS:
            raw_group = (
                image_data.get("Size", {}).get(group, {})
                if isinstance(image_data, dict)
                and isinstance(image_data.get("Size", {}), dict)
                else {}
            )
            raw_values = (
                raw_group.get(key, [])
                if isinstance(raw_group, dict) else []
            )
            if not isinstance(raw_values, (list, tuple)):
                raw_values = []

            for index, raw_value in enumerate(raw_values, start=1):
                number = _finite_number(raw_value)
                if number is None:
                    invalid_values += 1
                    continue
                grouped_values[(label, unit)].append(number)
                detail_rows.append([
                    str(image_name), label, index, number, unit
                ])

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = manifest.get("run_id", os.path.basename(os.path.abspath(output_dir)))
    settings = manifest.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    with PdfPages(output_path) as pdf:
        mpl.rcParams.update({
            "font.family": "serif",
            "font.serif": ["Liberation Serif", "DejaVu Serif"],
            "font.size": 8,
            "axes.titlesize": 11,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        })
        # Compact manuscript-style narrative using saved measurements only.
        try:
            narrative = generate_narrative(output_dir)
            _write_manuscript(
                pdf, narrative, run_id, image_count, total_objects,
                timestamp, manifest, settings
            )
        except (IOError, OSError, ValueError, TypeError) as exc:
            _write_text_page(
                pdf,
                "Offline Narrative",
                [
                    "The narrative could not be generated from saved data.",
                    "Error: {}".format(exc),
                    "The remaining report sections will still be generated."
                ]
            )

        # Build the three summary tables together so small datasets do not
        # create several mostly empty pages.
        stats_rows = []
        for (label, unit), values in sorted(grouped_values.items()):
            stats = _summary_stats(values)
            if stats:
                stats_rows.append([
                    label, unit, stats["count"],
                    "{:.4g}".format(stats["mean"]),
                    "{:.4g}".format(stats["median"]),
                    (
                        "{:.4g}".format(stats["std"])
                        if stats["std"] is not None
                        else "N/A (n=1)"
                    ),
                    "{:.4g}".format(stats["min"]),
                    "{:.4g}".format(stats["max"]),
                ])

        image_rows = []
        for image_name, item in sorted(image_counts.items()):
            image_rows.append([
                str(image_name), item["unit"],
                item["counts"]["Rods"],
                item["counts"]["Spheres"],
                item["counts"]["Triangles"],
                item["counts"]["Cubes"],
            ])

        all_image_names = sorted(
            set(row[0] for row in image_rows) |
            set(str(row[0]) for row in detail_rows)
        )
        image_id_by_name = {
            name: "IMG-{:03d}".format(index)
            for index, name in enumerate(all_image_names, start=1)
        }

        id_rows = [
            [
                image_id_by_name[row[0]], row[1], row[2],
                row[3], row[4], row[5]
            ]
            for row in image_rows
        ]
        filename_lookup = [
            [image_id_by_name[name], name]
            for name in all_image_names
        ]

        # Tables use the same column-header style and fixed vertical positions.
        # Each table starts below the page heading/subtitle.
        summary_sections = [
            (
                "Descriptive Statistics",
                stats_rows,
                [
                    "Measurement", "Unit", "N", "Mean", "Median",
                    "Std. dev.", "Minimum", "Maximum"
                ],
                [0.08, 0.625, 0.84, 0.235],
                "center",
                None,
            ),
            (
                "Per-Image Results",
                id_rows,
                [
                    "Image ID", "Unit", "Rods", "Spheres",
                    "Triangles", "Cubes"
                ],
                [0.08, 0.405, 0.84, 0.175],
                "center",
                None,
            ),
            (
                "Image Filename Lookup",
                filename_lookup,
                ["Image ID", "Full Original Filename"],
                [0.07, 0.105, 0.86, 0.255],
                "left",
                [0.22, 0.78],
            ),
        ]

        # Use one page for short tables. Larger tables are emitted on their own
        # pages, split into safe chunks so that all rows remain present.
        can_share = (
            len(stats_rows) <= 4
            and len(id_rows) <= 4
            and len(filename_lookup) <= 4
        )

        if can_share:
            fig, ax = _new_page(
                "Measurement Summary",
                "Summary statistics, per-image object counts, and original filename lookup."
            )
            section_positions = [
                (summary_sections[0], [0.08, 0.625, 0.84, 0.235], 8.5),
                (summary_sections[1], [0.08, 0.405, 0.84, 0.175], 7.5),
                (summary_sections[2], [0.07, 0.105, 0.86, 0.255], 7.5),
            ]

            for section, bounds, fontsize in section_positions:
                title, rows, headers, unused_bounds, cell_loc, col_widths = section
                ax.text(
                    bounds[0], bounds[1] + bounds[3] + 0.012,
                    title, transform=ax.transAxes,
                    fontsize=9, fontweight="bold",
                    fontfamily="serif", color="#202020",
                    va="bottom"
                )
                if rows:
                    _add_table(
                        fig, rows, headers, bounds,
                        fontsize=fontsize, cell_loc=cell_loc,
                        col_widths=col_widths
                    )
                else:
                    ax.text(
                        bounds[0], bounds[1] + bounds[3] - 0.025,
                        "No data available.",
                        transform=ax.transAxes, fontsize=7,
                        fontfamily="serif", color="#555555",
                        va="top"
                    )
            pdf.savefig(fig, bbox_inches="tight")
        else:
            for title, rows, headers, bounds, cell_loc, col_widths in summary_sections:
                if not rows:
                    _write_text_page(pdf, title, ["No data available."])
                    continue

                # Use a smaller, readable chunk size for the full-page table.
                chunk_size = 24 if title != "Image Filename Lookup" else 18
                for offset in range(0, len(rows), chunk_size):
                    chunk = rows[offset:offset + chunk_size]
                    fig, ax = _new_page(title)
                    table_bounds = [0.07, 0.105, 0.86, 0.77]
                    _add_table(
                        fig, chunk, headers, table_bounds,
                        fontsize=7, cell_loc=cell_loc,
                        col_widths=col_widths
                    )
                    pdf.savefig(fig, bbox_inches="tight")

        # Histograms, each restricted to a single measurement/unit group.
        for (label, unit), values in sorted(grouped_values.items()):
            if not values:
                continue
            fig = Figure(figsize=PAGE_SIZE, facecolor="white")
            ax = fig.add_subplot(111)
            ax.hist(values, bins="auto", edgecolor="black", alpha=0.8)
            ax.set_title("{} Distribution".format(label), fontsize=15)
            ax.set_xlabel("Measurement value ({})".format(unit))
            ax.set_ylabel("Frequency")
            ax.grid(True, alpha=0.2)
            fig.subplots_adjust(
                left=0.12, bottom=0.14, right=0.94, top=0.88
            )
            pdf.savefig(fig, bbox_inches="tight")

        # Available annotated images, limited to keep reports manageable.
        annotated_dir = os.path.join(output_dir, "annotated_subfigures_png")
        annotated_paths = []
        if os.path.isdir(annotated_dir):
            annotated_paths = sorted(
                os.path.join(annotated_dir, name)
                for name in os.listdir(annotated_dir)
                if name.lower().endswith((".png", ".jpg", ".jpeg"))
            )

        image_limit = 12
        for image_path in annotated_paths[:image_limit]:
            try:
                with Image.open(image_path) as source_image:
                    image = source_image.convert("RGB")
                fig = Figure(figsize=PAGE_SIZE, facecolor="white")
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.set_title(
                    "Annotated Image: {}".format(os.path.basename(image_path)),
                    fontsize=10, pad=12
                )
                ax.imshow(image)
                fig.subplots_adjust(
                    left=0.06, bottom=0.06, right=0.94, top=0.88
                )
                pdf.savefig(fig, bbox_inches="tight")
            except (OSError, ValueError):
                continue

        # Keep annotated-image availability information with the final
        # limitations/provenance section instead of creating a separate
        # text-only page.
        annotated_notes = []
        if len(annotated_paths) > image_limit:
            annotated_notes = [
                "The report includes the first {} annotated images in "
                "alphabetical order.".format(image_limit),
                "{} additional annotated images were available and are "
                "not embedded in this PDF.".format(
                    len(annotated_paths) - image_limit
                ),
                "All images remain available in: {}".format(annotated_dir),
            ]
        elif not annotated_paths:
            annotated_notes = [
                "No annotated images were found in the expected output folder."
            ]

        # Detailed, paginated measurement appendix.
        if detail_rows:
            for start in range(0, len(detail_rows), 38):
                fig, ax = _new_page(
                    "Appendix: Individual Measurements",
                    "Only finite numeric values from the saved measurement arrays are listed."
                )
                rows = detail_rows[start:start + 38]
                _add_table(
                    fig,
                    [
                        [
                            image_id_by_name.get(str(row[0]), str(row[0])),
                            row[1], row[2], "{:.8g}".format(row[3]), row[4]
                        ]
                        for row in rows
                    ],
                    ["Image", "Measurement", "Index", "Value", "Unit"],
                    [0.08, 0.105, 0.84, 0.77],
                    fontsize=7
                )
                pdf.savefig(fig, bbox_inches="tight")

        # Limitations and provenance.
        limitations = [
            "This document is a generated report of saved software output, not "
            "a peer-reviewed paper or an independent validation of the analysis.",
            "Object counts reflect the configured measurement arrays in sizes.json.",
            "Images with unknown units are explicitly labeled; their numeric "
            "values are not combined with values from known units.",
            "Statistics describe the saved measurements and do not establish "
            "statistical significance, causality, or general scientific conclusions.",
            "Invalid or non-finite measurement values omitted from the report: "
            "{}.".format(invalid_values),
            "Images with unknown units: {}".format(
                ", ".join(missing_unit_images) if missing_unit_images else "None"
            ),
            "Annotated images embedded: {} of {} available.".format(
                min(len(annotated_paths), image_limit), len(annotated_paths)
            ),
            "Source files and the complete set of outputs remain in the run folder.",
        ]
        limitations.extend(annotated_notes)
        _write_text_page(pdf, "Limitations and Data Provenance", limitations)

    return output_path
