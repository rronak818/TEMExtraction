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

    def percentile(fraction):
        position = (count - 1) * fraction
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return values[lower]
        weight = position - lower
        return values[lower] + (values[upper] - values[lower]) * weight

    q1 = percentile(0.25)
    q3 = percentile(0.75)
    if count > 1:
        variance = sum((v - mean) ** 2 for v in values) / float(count - 1)
        std_dev = math.sqrt(variance)
        cv = (std_dev / abs(mean) * 100.0) if mean != 0 else None
    else:
        variance = None
        std_dev = None
        cv = None
    return {
        "count": count, "mean": mean, "median": median,
        "std": std_dev, "variance": variance,
        "min": values[0], "max": values[-1],
        "range": values[-1] - values[0],
        "q1": q1, "q3": q3, "iqr": q3 - q1, "cv": cv
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
        "figure_caption": ParagraphStyle(
            "TEMFigureCaption", parent=base["Italic"], fontName="Times-Italic",
            fontSize=8, leading=10, alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
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


def _histogram_flowable(label, unit, values, max_width, max_height=88 * mm):
    """Create a histogram with mean/median references and a box plot."""
    values = sorted(values)
    if not values:
        return None

    mean = sum(values) / float(len(values))
    count = len(values)
    median = (
        values[count // 2] if count % 2
        else (values[count // 2 - 1] + values[count // 2]) / 2.0
    )

    fig = Figure(figsize=(7.0, 4.3), dpi=130, facecolor="white")
    histogram_ax = fig.add_subplot(211)
    histogram_ax.hist(
        values, bins="auto", edgecolor="#243746", color="#8DAFC4"
    )
    histogram_ax.axvline(
        mean, color="#B04A4A", linestyle="--", linewidth=1.5,
        label="Mean: {:.4g}".format(mean)
    )
    histogram_ax.axvline(
        median, color="#287A58", linestyle=":", linewidth=1.8,
        label="Median: {:.4g}".format(median)
    )
    histogram_ax.set_title(
        "{} Distribution (n={})".format(label, count), fontsize=10
    )
    histogram_ax.set_xlabel("Measurement value ({})".format(unit), fontsize=8)
    histogram_ax.set_ylabel("Frequency", fontsize=8)
    histogram_ax.tick_params(axis="both", labelsize=7)
    histogram_ax.grid(True, alpha=0.2)
    histogram_ax.legend(fontsize=7, loc="best")

    box_ax = fig.add_subplot(212)
    box_ax.boxplot(values, vert=False, patch_artist=True, widths=0.45,
                   boxprops={"facecolor": "#D7E5ED", "color": "#243746"},
                   medianprops={"color": "#287A58", "linewidth": 1.5},
                   whiskerprops={"color": "#243746"},
                   capprops={"color": "#243746"},
                   flierprops={"marker": "o", "markersize": 3,
                               "markerfacecolor": "#B04A4A",
                               "markeredgecolor": "#B04A4A"})
    box_ax.set_xlabel("Measurement value ({})".format(unit), fontsize=8)
    box_ax.set_yticks([1])
    box_ax.set_yticklabels(["All values"], fontsize=7)
    box_ax.tick_params(axis="x", labelsize=7)
    box_ax.grid(True, axis="x", alpha=0.2)
    if count == 1:
        box_ax.text(
            0.5, 0.72, "n=1: variability cannot be assessed from one value",
            transform=box_ax.transAxes, ha="center", va="center", fontsize=7
        )

    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.10, top=0.93, hspace=0.62)
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
    flow_image.hAlign = "CENTER"
    flow_image._tem_stream = stream
    return flow_image


def _annotated_flowable(path, max_width, max_height=125 * mm):
    """Embed an existing annotated image at a readable, centered size."""
    try:
        with PILImage.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((2000, 2000), PILImage.ANTIALIAS)
            stream = BytesIO()
            image.save(stream, format="JPEG", quality=94)
        stream.seek(0)
        flow_image = Image(stream)
        scale = min(
            max_width / float(flow_image.imageWidth),
            max_height / float(flow_image.imageHeight),
            1.0
        )
        flow_image.drawWidth = flow_image.imageWidth * scale
        flow_image.drawHeight = flow_image.imageHeight * scale
        flow_image.hAlign = "CENTER"
        flow_image._tem_stream = stream
        return flow_image
    except (OSError, ValueError):
        return None


def generate_pdf_report(output_dir, output_path):
    """Build a flowing, numbered research-paper-style PDF from saved results."""
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

    for image_name, image_data in data.items():
        unit = _valid_unit(
            image_data.get("Unit") if isinstance(image_data, dict) else None
        )
        if unit == "Unknown units":
            missing_unit_images.append(str(image_name))

        counts = {}
        for group, key, label in OBJECT_COUNT_KEYS:
            values = _get_values(image_data, group, key)
            counts[label] = len(values)
            total_objects += len(values)

        image_counts[str(image_name)] = {"unit": unit, "counts": counts}

        size_data = (
            image_data.get("Size", {})
            if isinstance(image_data, dict) else {}
        )
        for group, key, label in MEASUREMENTS:
            raw_group = (
                size_data.get(group, {})
                if isinstance(size_data, dict) else {}
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
                detail_rows.append(
                    [str(image_name), label, index, number, unit]
                )

    all_image_names = sorted(
        set(image_counts.keys()) |
        set(str(row[0]) for row in detail_rows)
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

    # Title block: retain the established report typography and page geometry.
    story.append(_p("TEMExtraction Microscopy Analysis Report", styles["title"]))
    story.append(_p("Run: {}".format(run_id), styles["subtitle"]))
    story.append(_p(
        "Generated: {} | Image records: {} | Recorded objects: {}".format(
            timestamp, len(data), total_objects
        ),
        styles["subtitle"]
    ))
    story.append(HRFlowable(
        width="100%", thickness=0.7,
        color=colors.HexColor("#9AA8B5"),
        spaceBefore=1 * mm, spaceAfter=3 * mm
    ))

    # Abstract remains generated from the existing deterministic narrative.
    try:
        narrative = generate_narrative(output_dir)
    except (IOError, OSError, ValueError, TypeError) as exc:
        narrative = {
            "abstract": [
                "The offline narrative could not be generated. Error: {}".format(exc)
            ],
            "methods": [],
            "results": [],
            "discussion": [],
            "conclusion": [],
        }

    story.append(_p("Abstract", styles["section"]))
    for paragraph in narrative.get("abstract", []):
        story.append(_p(paragraph, styles["body"]))

    # This introduction describes the scope of the saved output, not new findings.
    story.append(_p("1. Introduction", styles["section"]))
    story.append(_p(
        "This report presents a descriptive organization of the microscopy "
        "measurements saved by TEMExtraction for the selected run. It brings "
        "together recorded object dimensions, per-image object counts, "
        "measurement distributions, and available annotated images. The report "
        "summarizes existing output files; it does not independently validate "
        "measurement accuracy or establish scientific conclusions.",
        styles["body"]
    ))

    story.append(_p("2. Materials and Methods", styles["section"]))
    for paragraph in narrative.get("methods", []):
        story.append(_p(paragraph, styles["body"]))

    story.append(_p("3. Results", styles["section"]))
    for paragraph in narrative.get("results", []):
        story.append(_p(paragraph, styles["body"]))

    # Table 1: expanded descriptive statistics, separated by measurement and unit.
    story.append(_p("3.1. Descriptive statistics", styles["subsection"]))
    story.append(_p("Table 1 summarizes the central tendency, dispersion and observed range of measurements recorded for each object category. The mean and median characterize central tendency, while the standard deviation, variance and interquartile range quantify different aspects of variability. The quartiles describe the central 50% of observations, whereas the minimum, maximum and range characterize the observed extremes. The coefficient of variation expresses dispersion relative to the mean where this comparison is meaningful.", styles["body"]))
    story.append(_p("These statistics provide complementary descriptions of the measurements within the analyzed dataset. Differences between the mean and median may reflect distributional asymmetry or the influence of extreme observations, although neither explanation can be established from these statistics alone. Estimates based on small samples, particularly single observations, provide limited information about variability. Comparisons should account for measurement units and the number of observations available.", styles["body"]))
    stats_rows = []
    for (label, unit), values in sorted(grouped_values.items()):
        stats = _summary_stats(values)
        if stats:
            stats_rows.append([
                label, unit, stats["count"], _fmt(stats["mean"]),
                _fmt(stats["median"]),
                _fmt(stats["std"]) if stats["std"] is not None else "N/A",
                _fmt(stats["variance"]) if stats["variance"] is not None else "N/A",
                _fmt(stats["q1"]), _fmt(stats["q3"]), _fmt(stats["iqr"]),
                _fmt(stats["min"]), _fmt(stats["max"]), _fmt(stats["range"]),
                _fmt(stats["cv"]) + "%" if stats["cv"] is not None else "N/A"
            ])

    story.append(_p(
        "Table 1. Descriptive statistics by measurement type and unit. Variance and standard deviation use the sample formula; quartiles use linear interpolation.",
        styles["caption"]
    ))
    if stats_rows:
        story.append(_make_table(
            ["Measurement", "Unit", "N", "Mean", "Median", "Std. dev.",
             "Variance", "Q1", "Q3", "IQR", "Minimum", "Maximum", "Range", "CV%"],
            stats_rows,
            [22 * mm, 14 * mm, 7 * mm, 12 * mm, 12 * mm, 13 * mm,
             13 * mm, 10 * mm, 10 * mm, 10 * mm, 11 * mm, 11 * mm, 10 * mm, 9 * mm],
            styles
        ))
    else:
        story.append(_p(
            "No valid numeric measurements were available.", styles["body"]
        ))

    # Table 2: per-image counts, totals, and contribution to the dataset.
    story.append(_p("3.2. Per-image object counts", styles["subsection"]))
    story.append(_p("Table 2 presents the distribution of recorded object counts across the analyzed images, including category-specific counts, total counts per image and each image's contribution to the dataset-wide object count. Aggregate totals describe the composition of the objects recorded by the analysis pipeline, while the average count per image summarizes the recorded counts across the dataset.", styles["body"]))
    story.append(_p("Differences in counts between images may reflect variation in image content, the number of visible objects, acquisition conditions or pipeline performance. Counts alone cannot distinguish between these explanations or establish detection accuracy. The reported categories represent the application's assigned measurement classes and should not be interpreted as independently validated object identities.", styles["body"]))
    image_rows = []
    category_totals = {"Rods": 0, "Spheres": 0, "Triangles": 0, "Cubes": 0}
    for name, item in sorted(image_counts.items()):
        counts = item["counts"]
        image_total = sum(counts.values())
        for category in category_totals:
            category_totals[category] += counts[category]
        contribution = (
            "{:.2f}%".format(image_total * 100.0 / total_objects)
            if total_objects else "N/A"
        )
        image_rows.append([
            image_id_by_name[name], name, item["unit"],
            counts["Rods"], counts["Spheres"], counts["Triangles"],
            counts["Cubes"], image_total, contribution
        ])

    image_total_count = len(image_counts)
    average_per_image = (
        total_objects / float(image_total_count) if image_total_count else 0.0
    )
    story.append(_p(
        "Dataset summary: {} images; {} recorded objects in total; average {:.2f} objects per image. Category totals — rods: {}, spheres: {}, triangles: {}, cubes: {}.".format(
            image_total_count, total_objects, average_per_image,
            category_totals["Rods"], category_totals["Spheres"],
            category_totals["Triangles"], category_totals["Cubes"]
        ),
        styles["body"]
    ))
    story.append(_p(
        "Table 2. Object counts per image. Contribution is each image's share of all recorded objects; percentages may not sum to exactly 100% because of rounding.",
        styles["caption"]
    ))
    if image_rows:
        image_rows.append([
            "TOTAL", "All images", "—", category_totals["Rods"],
            category_totals["Spheres"], category_totals["Triangles"],
            category_totals["Cubes"], total_objects,
            "100.00%" if total_objects else "N/A"
        ])
        story.append(_make_table(
            ["Image ID", "Original filename", "Unit", "Rods", "Spheres",
             "Triangles", "Cubes", "Total", "Dataset %"],
            image_rows,
            [15 * mm, 54 * mm, 15 * mm, 12 * mm, 12 * mm,
             13 * mm, 12 * mm, 14 * mm, 16 * mm],
            styles
        ))
    else:
        story.append(_p("No per-image results available.", styles["body"]))

    # Numbered figures flow naturally after the results tables.
    story.append(_p("3.3. Measurement distributions", styles["subsection"]))
    story.append(_p("The distribution plots characterize the frequency and dispersion of recorded measurements for each measurement type and unit. Histograms show the observed frequency pattern, while the mean and median provide reference points for central tendency. The accompanying box plots summarize the median, interquartile range and spread according to the plotting convention used. Observations beyond the whiskers may warrant further examination but should not automatically be classified as erroneous.", styles["body"]))
    story.append(_p("Distributional patterns should be interpreted in conjunction with sample size and the underlying image data. Where few measurements are available, apparent patterns may be unstable, and conclusions about variability, asymmetry or unusual observations should remain cautious. These plots describe the measurements obtained in this analysis; they do not by themselves establish the properties of a wider particle population.", styles["body"]))
    figure_number = 1
    if grouped_values:
        for (label, unit), values in sorted(grouped_values.items()):
            if not values:
                continue
            story.append(_p(
                "Figure {}. Distribution of {} measurements (unit: {}; n={})."
                .format(figure_number, label, unit, len(values)),
                styles["figure_caption"]
            ))
            distribution_plot = _histogram_flowable(
                label, unit, values, usable_width, max_height=88 * mm
            )
            if distribution_plot is not None:
                story.append(distribution_plot)
                story.append(Spacer(1, 2 * mm))
            figure_number += 1
    else:
        story.append(_p(
            "No valid measurements were available for distribution plots.",
            styles["body"]
        ))

    # Annotated images retain the previous embedding limit and sort order.
    annotated_dir = os.path.join(output_dir, "annotated_subfigures_png")
    annotated_paths = []
    if os.path.isdir(annotated_dir):
        annotated_paths = sorted(
            os.path.join(annotated_dir, name)
            for name in os.listdir(annotated_dir)
            if name.lower().endswith((".png", ".jpg", ".jpeg"))
        )

    story.append(_p("3.4. Annotated microscopy images", styles["subsection"]))
    story.append(_p("The annotated microscopy images provide visual context for the objects marked during the analysis pipeline. They complement the numerical summaries by allowing the recorded results to be considered alongside the image regions represented in the saved annotations. These figures document the available analysis output rather than independently validating detection, classification or measurement accuracy.", styles["body"]))
    story.append(_p("The annotations should therefore be interpreted as records of the pipeline output. Confirmation of object identity and measurement reliability would require appropriate visual review or comparison against independently established reference measurements. Where an annotation filename cannot be reliably linked to its original input image, that correspondence remains unspecified.", styles["body"]))
    embedded_count = 0
    for path in annotated_paths[:IMAGE_LIMIT]:
        flow_image = _annotated_flowable(path, usable_width)
        if flow_image is None:
            continue
        embedded_count += 1
        caption = _p(
            "Figure {}. Pipeline-generated annotated microscopy image (file: {}). The displayed annotation is preserved from the saved analysis output; its hash-based filename is not treated as an original source-image identifier."
            .format(figure_number, os.path.basename(path)),
            styles["figure_caption"]
        )
        story.append(KeepTogether([
            flow_image, Spacer(1, 1 * mm), caption
        ]))
        figure_number += 1

    if embedded_count == 0:
        story.append(_p(
            "No readable annotated images were available to embed.",
            styles["body"]
        ))

    story.append(_p("4. Discussion", styles["section"]))
    for paragraph in narrative.get("discussion", []):
        story.append(_p(paragraph, styles["body"]))

    story.append(_p("5. Conclusion", styles["section"]))
    for paragraph in narrative.get("conclusion", []):
        story.append(_p(paragraph, styles["body"]))

    # Appendix A: preserve every valid saved numeric measurement.
    story.append(_p(
        "Appendix A. Individual Measurements", styles["section"]
    ))
    story.append(_p(
        "Table A1. Individual numeric measurements with image identifiers.",
        styles["caption"]
    ))
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
        story.append(_p(
            "No valid individual measurements were available.", styles["body"]
        ))

    # Appendix B: filename lookup appears only here, avoiding duplicate tables.
    story.append(_p(
        "Appendix B. Image Filename Lookup", styles["section"]
    ))
    story.append(_p(
        "Table B1. Mapping between report image identifiers and original filenames.",
        styles["caption"]
    ))
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

    # Limitations and provenance remain explicit and data-grounded.
    story.append(_p(
        "Limitations and Data Provenance", styles["section"]
    ))
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
            embedded_count, len(annotated_paths)
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
            "The first {} annotated images in alphabetical order were considered for embedding.".format(IMAGE_LIMIT),
            "{} additional annotated images were not embedded; they remain available in {}.".format(
                max(0, len(annotated_paths) - IMAGE_LIMIT), annotated_dir
            )
        ])
    elif not annotated_paths:
        limitations.append(
            "No annotated images were found in the expected output folder."
        )

    for paragraph in limitations:
        story.append(_p(paragraph, styles["body"]))

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
