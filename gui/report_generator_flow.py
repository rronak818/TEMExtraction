# -*- coding: utf-8 -*-
"""Flow-based TEMExtraction PDF report renderer.

Uses saved measurements only. Compatible with Python 3.6.
This module is intentionally separate from report_generator.py
until layout and content verification are complete.
"""

from __future__ import print_function

import json
import math
import os
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether, HRFlowable
)

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

IMAGE_LIMIT = 12


def _valid_unit(raw_unit):
    if not isinstance(raw_unit, str):
        return "Unknown units"
    unit = raw_unit.strip()
    if not unit or unit.lower() in ("none", "nan", "unknown", "n/a"):
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
        values[count // 2] if count % 2
        else (values[count // 2 - 1] + values[count // 2]) / 2.0
    )
    if count > 1:
        variance = sum((v - mean) ** 2 for v in values) / float(count - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = None
    return {
        "count": count, "mean": mean, "median": median,
        "std": std_dev, "min": values[0], "max": values[-1]
    }


def _fmt(value):
    return "{:.4g}".format(value)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TEMTitle", parent=base["Title"], fontName="Times-Bold",
            fontSize=19, leading=23, alignment=TA_LEFT,
            textColor=colors.HexColor("#202D3A"), spaceAfter=5 * mm
        ),
        "subtitle": ParagraphStyle(
            "TEMSubtitle", parent=base["Normal"], fontName="Times-Roman",
            fontSize=9, leading=12, textColor=colors.HexColor("#586574"),
            spaceAfter=3 * mm
        ),
        "section": ParagraphStyle(
            "TEMSection", parent=base["Heading1"], fontName="Times-Bold",
            fontSize=14, leading=17, textColor=colors.HexColor("#243B53"),
            spaceBefore=5 * mm, spaceAfter=2 * mm, keepWithNext=True
        ),
        "subsection": ParagraphStyle(
            "TEMSubsection", parent=base["Heading2"], fontName="Times-Bold",
            fontSize=10.5, leading=13, textColor=colors.HexColor("#34495E"),
            spaceBefore=3 * mm, spaceAfter=1.5 * mm, keepWithNext=True
        ),
        "body": ParagraphStyle(
            "TEMBody", parent=base["BodyText"], fontName="Times-Roman",
            fontSize=9.2, leading=12.2, alignment=TA_LEFT,
            spaceAfter=2.2 * mm, splitLongWords=1
        ),
        "small": ParagraphStyle(
            "TEMSmall", parent=base["BodyText"], fontName="Times-Roman",
            fontSize=7.6, leading=9.5, spaceAfter=1.5 * mm
        ),
        "caption": ParagraphStyle(
            "TEMCaption", parent=base["Italic"], fontName="Times-Italic",
            fontSize=8, leading=10, textColor=colors.HexColor("#555555"),
            spaceBefore=1 * mm, spaceAfter=3 * mm
        ),
        "table_header": ParagraphStyle(
            "TEMTableHeader", parent=base["Normal"],
            fontName="Times-Bold", fontSize=7.2, leading=8.5
        ),
        "table_cell": ParagraphStyle(
            "TEMTableCell", parent=base["Normal"],
            fontName="Times-Roman", fontSize=7.1, leading=8.6,
            splitLongWords=1
        ),
    }


def _p(text, style):
    """Escape data strings before placing them in ReportLab paragraphs."""
    return Paragraph(escape(str(text)), style)


def _cell(value, style):
    return Paragraph(escape(str(value)), style)


def _make_table(headers, rows, widths, styles, repeat=True):
    header_cells = [_cell(value, styles["table_header"]) for value in headers]
    body_rows = [
        [_cell(value, styles["table_cell"]) for value in row]
        for row in rows
    ]
    table = Table(
        [header_cells] + body_rows,
        colWidths=widths,
        repeatRows=1 if repeat else 0,
        hAlign="LEFT",
        splitByRow=1
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#203040")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B9C2CC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F7F9FB")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _on_page(canvas, document):
    canvas.saveState()
    page_width, page_height = A4
    canvas.setStrokeColor(colors.HexColor("#CBD2D9"))
    canvas.setLineWidth(0.45)
    canvas.line(18 * mm, page_height - 13 * mm,
                page_width - 18 * mm, page_height - 13 * mm)
    canvas.setFont("Times-Roman", 7.5)
    canvas.setFillColor(colors.HexColor("#687582"))
    canvas.drawString(18 * mm, 9 * mm, "TEMExtraction | Microscopy Analysis Report")
    canvas.drawRightString(
        page_width - 18 * mm, 9 * mm, "Page {}".format(document.page)
    )
    canvas.restoreState()


def _histogram_flowable(label, unit, values, max_width, max_height=78 * mm):
    """Create an in-memory histogram image suitable for natural page flow."""
    fig = Figure(figsize=(7.0, 3.2), dpi=130, facecolor="white")
    ax = fig.add_subplot(111)
    ax.hist(values, bins="auto", edgecolor="#243746", color="#8DAFC4")
    ax.set_title("{} Distribution".format(label), fontsize=11)
    ax.set_xlabel("Measurement value ({})".format(unit), fontsize=9)
    ax.set_ylabel("Frequency", fontsize=9)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()

    stream = BytesIO()
    fig.savefig(stream, format="png", dpi=130, bbox_inches="tight")
    stream.seek(0)
    flow_image = Image(stream)
    scale = min(
        max_width / float(flow_image.imageWidth),
        max_height / float(flow_image.imageHeight),
        1.0
    )
    flow_image.drawWidth = flow_image.imageWidth * scale
    flow_image.drawHeight = flow_image.imageHeight * scale
    flow_image.hAlign = "LEFT"
    # Keep the image stream alive for ReportLab while building the document.
    flow_image._tem_stream = stream
    return flow_image


def _annotated_flowable(path, max_width, max_height=100 * mm):
    try:
        with PILImage.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((1600, 1600), PILImage.ANTIALIAS)
            stream = BytesIO()
            image.save(stream, format="JPEG", quality=90)
        stream.seek(0)
        flow_image = Image(stream)
        scale = min(
            max_width / float(flow_image.imageWidth),
            max_height / float(flow_image.imageHeight),
            1.0
        )
        flow_image.drawWidth = flow_image.imageWidth * scale
        flow_image.drawHeight = flow_image.imageHeight * scale
        flow_image.hAlign = "LEFT"
        flow_image._tem_stream = stream
        return flow_image
    except (OSError, ValueError):
        return None


def generate_pdf_report(output_dir, output_path):
    """Build a flowing research-style PDF from saved TEMExtraction results."""
    sizes_path = os.path.join(output_dir, "sizes.json")
    if not os.path.isfile(sizes_path):
        raise ValueError("The selected output folder has no sizes.json file.")

    with open(sizes_path, "r") as source:
        data = json.load(source)
    if not isinstance(data, dict) or not data:
        raise ValueError("sizes.json contains no usable image results.")

    manifest = {}
    manifest_path = os.path.join(output_dir, "run_manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r") as source:
                loaded = json.load(source)
            if isinstance(loaded, dict):
                manifest = loaded
        except (OSError, ValueError):
            manifest = {}

    image_counts = {}
    grouped_values = defaultdict(list)
    detail_rows = []
    total_objects = 0
    invalid_values = 0
    missing_unit_images = []
    known_units = set()

    for image_name, image_data in data.items():
        unit = _valid_unit(
            image_data.get("Unit") if isinstance(image_data, dict) else None
        )
        if unit == "Unknown units":
            missing_unit_images.append(str(image_name))
        else:
            known_units.add(unit)

        counts = {}
        for group, key, label in OBJECT_COUNT_KEYS:
            values = _get_values(image_data, group, key)
            counts[label] = len(values)
            total_objects += len(values)

        image_counts[str(image_name)] = {"unit": unit, "counts": counts}

        for group, key, label in MEASUREMENTS:
            size_data = (
                image_data.get("Size", {})
                if isinstance(image_data, dict) else {}
            )
            raw_group = size_data.get(group, {}) if isinstance(size_data, dict) else {}
            raw_values = raw_group.get(key, []) if isinstance(raw_group, dict) else []
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

    all_image_names = sorted(
        set(image_counts.keys()) | set(str(row[0]) for row in detail_rows)
    )
    image_id_by_name = {
        name: "IMG-{:03d}".format(index)
        for index, name in enumerate(all_image_names, start=1)
    }

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = manifest.get(
        "run_id", os.path.basename(os.path.abspath(output_dir))
    )
    settings = manifest.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    styles = _styles()
    story = []
    page_width, page_height = A4
    usable_width = page_width - 36 * mm

    story.append(_p("TEMExtraction Microscopy Analysis Report", styles["title"]))
    story.append(_p("Run: {}".format(run_id), styles["subtitle"]))
    story.append(_p(
        "Generated: {} | Image records: {} | Recorded objects: {}".format(
            timestamp, len(data), total_objects
        ),
        styles["subtitle"]
    ))
    story.append(HRFlowable(
        width="100%", thickness=0.7, color=colors.HexColor("#9AA8B5"),
        spaceBefore=1 * mm, spaceAfter=3 * mm
    ))

    # Narrative remains generated by the existing deterministic function.
    try:
        narrative = generate_narrative(output_dir)
        story.append(_p("Abstract", styles["section"]))
        for text in narrative.get("abstract", []):
            story.append(_p(text, styles["body"]))

        story.append(_p("Materials and Methods", styles["section"]))
        for text in narrative.get("methods", []):
            story.append(_p(text, styles["body"]))

        story.append(_p("Results", styles["section"]))
        for text in narrative.get("results", []):
            story.append(_p(text, styles["body"]))

        story.append(_p("Discussion", styles["section"]))
        for text in narrative.get("discussion", []):
            story.append(_p(text, styles["body"]))

        story.append(_p("Conclusion", styles["section"]))
        for text in narrative.get("conclusion", []):
            story.append(_p(text, styles["body"]))
    except (IOError, OSError, ValueError, TypeError) as exc:
        story.append(_p("Offline Narrative", styles["section"]))
        story.append(_p(
            "The narrative could not be generated. Error: {}".format(exc),
            styles["body"]
        ))

    # Descriptive statistics, retaining each measurement/unit group separately.
    story.append(_p("Descriptive Statistics", styles["section"]))
    stats_rows = []
    for (label, unit), values in sorted(grouped_values.items()):
        stats = _summary_stats(values)
        if stats:
            stats_rows.append([
                label, unit, stats["count"], _fmt(stats["mean"]),
                _fmt(stats["median"]),
                _fmt(stats["std"]) if stats["std"] is not None else "N/A (n=1)",
                _fmt(stats["min"]), _fmt(stats["max"])
            ])
    if stats_rows:
        story.append(_make_table(
            ["Measurement", "Unit", "N", "Mean", "Median",
             "Std. dev.", "Minimum", "Maximum"],
            stats_rows,
            [27 * mm, 19 * mm, 10 * mm, 18 * mm, 18 * mm,
             20 * mm, 18 * mm, 18 * mm],
            styles
        ))
    else:
        story.append(_p("No valid numeric measurements were available.", styles["body"]))

    # Per-image counts and stable image IDs.
    story.append(_p("Per-Image Results", styles["section"]))
    image_rows = []
    for name, item in sorted(image_counts.items()):
        image_rows.append([
            image_id_by_name[name], name, item["unit"],
            item["counts"]["Rods"], item["counts"]["Spheres"],
            item["counts"]["Triangles"], item["counts"]["Cubes"]
        ])
    if image_rows:
        story.append(_make_table(
            ["Image ID", "Original filename", "Unit",
             "Rods", "Spheres", "Triangles", "Cubes"],
            image_rows,
            [17 * mm, 66 * mm, 19 * mm, 12 * mm, 15 * mm, 18 * mm, 12 * mm],
            styles
        ))
    else:
        story.append(_p("No per-image results available.", styles["body"]))

    story.append(_p("Image Filename Lookup", styles["section"]))
    lookup_rows = [
        [image_id_by_name[name], name] for name in all_image_names
    ]
    if lookup_rows:
        story.append(_make_table(
            ["Image ID", "Full Original Filename"],
            lookup_rows, [25 * mm, 154 * mm], styles
        ))
    else:
        story.append(_p("No image filenames available.", styles["body"]))

    # Histograms flow after the summary tables; no forced page per figure.
    if grouped_values:
        story.append(_p("Measurement Distributions", styles["section"]))
        for (label, unit), values in sorted(grouped_values.items()):
            if not values:
                continue
            story.append(_p(
                "{} — {} (n={})".format(label, unit, len(values)),
                styles["subsection"]
            ))
            story.append(_histogram_flowable(
                label, unit, values, usable_width, max_height=65 * mm
            ))
            story.append(Spacer(1, 2 * mm))

    # Embed up to the same limit as the existing renderer.
    annotated_dir = os.path.join(output_dir, "annotated_subfigures_png")
    annotated_paths = []
    if os.path.isdir(annotated_dir):
        annotated_paths = sorted(
            os.path.join(annotated_dir, name)
            for name in os.listdir(annotated_dir)
            if name.lower().endswith((".png", ".jpg", ".jpeg"))
        )

    if annotated_paths:
        story.append(_p("Annotated Images", styles["section"]))
        for path in annotated_paths[:IMAGE_LIMIT]:
            flow_image = _annotated_flowable(path, usable_width)
            if flow_image is None:
                continue
            caption = _p(
                "Annotated image: {}".format(os.path.basename(path)),
                styles["caption"]
            )
            story.append(KeepTogether([flow_image, caption]))

    # Individual saved numeric values, including image ID, measurement index,
    # unit, and original filename lookup above.
    story.append(_p("Appendix: Individual Measurements", styles["section"]))
    if detail_rows:
        appendix_rows = [
            [
                image_id_by_name.get(str(row[0]), str(row[0])),
                row[1], row[2], "{:.8g}".format(row[3]), row[4]
            ]
            for row in detail_rows
        ]
        story.append(_make_table(
            ["Image ID", "Measurement", "Index", "Value", "Unit"],
            appendix_rows,
            [24 * mm, 42 * mm, 17 * mm, 32 * mm, 24 * mm],
            styles
        ))
    else:
        story.append(_p("No valid individual measurements were available.", styles["body"]))

    # Limitations and provenance.
    story.append(_p("Limitations and Data Provenance", styles["section"]))
    limitations = [
        "This document reports saved software output; it is not a peer-reviewed paper or independent validation of the analysis.",
        "Object counts reflect the configured measurement arrays in sizes.json.",
        "Values with unknown units are not combined with values from known units.",
        "Descriptive statistics do not establish statistical significance, causality, or general scientific conclusions.",
        "Invalid or non-finite measurement values omitted from numeric summaries: {}.".format(invalid_values),
        "Images with unknown units: {}.".format(
            ", ".join(missing_unit_images) if missing_unit_images else "None"
        ),
        "Annotated images embedded: {} of {} available.".format(
            min(len(annotated_paths), IMAGE_LIMIT), len(annotated_paths)
        ),
        "Run ID: {}.".format(run_id),
        "Recorded input mode: {}.".format(manifest.get("input_mode", "Not recorded")),
        "Recorded run status: {}.".format(manifest.get("status", "Not recorded")),
        "Generation timestamp: {}.".format(timestamp),
        "Recorded settings: {}.".format(
            json.dumps(settings, sort_keys=True, ensure_ascii=True)
            if settings else "No settings recorded"
        ),
        "Source files and complete outputs remain in the run folder.",
        "Measurement accuracy, segmentation quality, calibration, representativeness, and independence of observations were not independently verified.",
        "References and citations are not invented or automatically supplied.",
        "Any publication-ready manuscript requires researcher review and confirmation of methods, results, and relevant literature."
    ]
    if len(annotated_paths) > IMAGE_LIMIT:
        limitations.extend([
            "The first {} annotated images in alphabetical order were embedded.".format(IMAGE_LIMIT),
            "{} additional annotated images were not embedded; they remain available in {}.".format(
                len(annotated_paths) - IMAGE_LIMIT, annotated_dir
            )
        ])
    elif not annotated_paths:
        limitations.append("No annotated images were found in the expected output folder.")

    for text in limitations:
        story.append(_p(text, styles["body"]))

    output_parent = os.path.dirname(os.path.abspath(output_path))
    if output_parent and not os.path.isdir(output_parent):
        os.makedirs(output_parent)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=19 * mm, bottomMargin=16 * mm,
        title="TEMExtraction Microscopy Analysis Report",
        author="TEMExtraction",
        subject="Saved microscopy measurements and analysis report"
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path
