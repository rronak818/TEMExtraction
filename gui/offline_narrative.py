# -*- coding: utf-8 -*-
"""Offline, data-driven scientific narrative generator for TEMExtraction.

No network, API key, additional package, or language model is required.
Python 3.6 compatible. Does not modify analysis measurements.
"""

from __future__ import print_function

import json
import math
import os

MEASUREMENTS = [
    ("rod", "length", "Rod length"),
    ("rod", "width", "Rod width"),
    ("sphere", "diameter", "Sphere diameter"),
    ("triangle", "height", "Triangle height"),
    ("cube", "side", "Cube side"),
]

OBJECTS = [
    ("rod", "length", "rods"),
    ("sphere", "diameter", "spheres"),
    ("triangle", "height", "triangles"),
    ("cube", "side", "cubes"),
]


def _number(value):
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _stats(values):
    values = sorted(values)
    if not values:
        return None

    count = len(values)
    mean = sum(values) / float(count)
    middle = count // 2
    if count % 2:
        median = values[middle]
    else:
        median = (values[middle - 1] + values[middle]) / 2.0

    variance = (
        sum((value - mean) ** 2 for value in values) / (count - 1)
        if count > 1 else None
    )

    return {
        "count": count,
        "mean": mean,
        "median": median,
        "std": math.sqrt(variance) if variance is not None else None,
        "min": values[0],
        "max": values[-1],
    }


def _format(value):
    return "{:.3f}".format(value)


def _get_measurements(image_data, group, key):
    if not isinstance(image_data, dict):
        return []

    sizes = image_data.get("Size", {})
    if not isinstance(sizes, dict):
        return []

    group_data = sizes.get(group, {})
    if not isinstance(group_data, dict):
        return []

    raw = group_data.get(key, [])
    if not isinstance(raw, (list, tuple)):
        return []

    return [
        number for number in (_number(item) for item in raw)
        if number is not None
    ]


def generate_narrative(output_dir):
    """Return research-paper sections derived from a saved TEMExtraction run."""
    sizes_path = os.path.join(output_dir, "sizes.json")
    manifest_path = os.path.join(output_dir, "run_manifest.json")

    if not os.path.isfile(sizes_path):
        raise IOError("Could not find saved measurements: {}".format(sizes_path))

    with open(sizes_path, "r") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Expected sizes.json to contain an image-keyed dictionary.")

    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r") as handle:
            loaded = json.load(handle)
            if isinstance(loaded, dict):
                manifest = loaded

    image_count = len(data)
    units = {}
    all_values = {}
    object_counts = {}
    stats_by_measurement = {}

    for image_name, image_data in data.items():
        unit = "Unknown units"
        if isinstance(image_data, dict):
            raw_unit = image_data.get("Unit")
            if isinstance(raw_unit, str) and raw_unit.strip():
                unit = raw_unit.strip()
        units[unit] = units.get(unit, 0) + 1

    for group, key, label in MEASUREMENTS:
        collected = []
        for image_data in data.values():
            collected.extend(_get_measurements(image_data, group, key))

        all_values[label] = collected
        stats_by_measurement[label] = _stats(collected)

    for group, key, label in OBJECTS:
        count = sum(
            len(_get_measurements(image_data, group, key))
            for image_data in data.values()
        )
        object_counts[label] = count

    total_objects = sum(object_counts.values())
    run_id = manifest.get("run_id", os.path.basename(os.path.abspath(output_dir)))
    input_mode = manifest.get("input_mode", "Not recorded")
    status = manifest.get("status", "Not recorded")

    unit_description = ", ".join(
        "{} ({})".format(unit, count)
        for unit, count in sorted(units.items())
    ) or "No unit information recorded"

    # Abstract
    abstract = [
        "This report summarizes microscopy measurements saved by "
        "TEMExtraction for run {}.".format(run_id),
        "The saved dataset contains {} image record(s) and {} measured "
        "object(s), counted using the configured object categories. "
        "Recorded units: {}.".format(
            image_count, total_objects, unit_description
        ),
    ]

    available = [
        (label, stats)
        for label, stats in stats_by_measurement.items()
        if stats is not None
    ]

    if available:
        highlights = []
        for label, stats in available:
            highlights.append(
                "{}: n={}, mean={}, median={}.".format(
                    label, stats["count"],
                    _format(stats["mean"]),
                    _format(stats["median"])
                )
            )
        abstract.append(
            "Descriptive measurements are summarized as follows: "
            + " ".join(highlights)
        )
    else:
        abstract.append(
            "No valid numeric measurements were found for the configured "
            "measurement categories. Quantitative conclusions cannot be drawn."
        )

    abstract.append(
        "These results describe the saved measurements only; they do not "
        "establish statistical significance, material properties, or causal "
        "relationships."
    )

    # Methods
    methods = [
        "The report was generated offline from the saved sizes.json file "
        "in the TEMExtraction output directory. No image analysis was rerun "
        "during report generation.",
        "Measurements were grouped by the object categories and measurement "
        "fields recorded by TEMExtraction: rod length and width, sphere "
        "diameter, triangle height, and cube side.",
        "For each available measurement category, descriptive statistics "
        "include sample count, arithmetic mean, median, sample standard "
        "deviation, minimum, and maximum. Invalid or non-finite numeric "
        "entries are excluded from these summaries.",
        "Recorded input mode: {}. Recorded run status: {}.".format(
            input_mode, status
        ),
        "Units were read from the saved image records. Values with different "
        "units must not be combined or directly compared without a valid "
        "unit conversion.",
        "This report describes the stored data and application workflow. "
        "It does not independently validate image segmentation, calibration, "
        "or measurement accuracy."
    ]

    # Results
    results = [
        "The dataset contains {} image record(s), with {} recorded object(s) "
        "across the configured categories.".format(image_count, total_objects),
        "Recorded unit distribution: {}.".format(unit_description),
    ]

    for label, stats in stats_by_measurement.items():
        if stats is None:
            results.append(
                "{}: no valid numeric measurements were available.".format(label)
            )
        else:
            std_text = (
                _format(stats["std"])
                if stats["std"] is not None
                else "not estimable (n=1)"
            )
            results.append(
                "{}: n={}, mean={}, median={}, standard deviation={}, "
                "minimum={}, maximum={}.".format(
                    label, stats["count"], _format(stats["mean"]),
                    _format(stats["median"]), std_text,
                    _format(stats["min"]), _format(stats["max"])
                )
            )

    results.append(
        "These summaries are calculated from the saved numeric values. "
        "A measurement count is not necessarily equivalent to an independent "
        "experimental sample count."
    )

    # Discussion
    discussion = [
        "The descriptive statistics provide a compact summary of the recorded "
        "dimensions and their observed ranges. The mean and median describe "
        "central tendency, while the standard deviation and range describe "
        "variation within the saved measurements.",
        "Differences between the mean and median may indicate an asymmetric "
        "distribution or influential observations, but these statistics alone "
        "do not establish the cause of that pattern.",
        "Interpretation depends on image quality, calibration, segmentation "
        "performance, sampling strategy, and whether observations are "
        "independent. Those factors should be checked against the original "
        "microscopy data and experimental records.",
        "No hypothesis tests, confidence intervals, material identification, "
        "or claims of statistical significance are generated by this module."
    ]

    # Conclusion
    conclusion = [
        "TEMExtraction produced a saved dataset containing {} image record(s) "
        "and {} recorded object(s) across its configured categories.".format(
            image_count, total_objects
        ),
        "The available descriptive statistics summarize the measurements "
        "present in this run. Any scientific interpretation should be "
        "confirmed against the original images, calibration information, "
        "and experimental context.",
        "This automatically generated narrative is a reporting aid, not a "
        "peer-reviewed paper or independent validation of the measurements."
    ]

    # Limitations
    limitations = [
        "The narrative is generated using deterministic templates; no LLM "
        "or external service is contacted.",
        "The report uses only the measurements and metadata saved in this run. "
        "Missing metadata is not inferred.",
        "Measurement accuracy, segmentation quality, scale calibration, "
        "sample representativeness, and independence of observations were not "
        "independently verified.",
        "References and citations are not invented or automatically supplied.",
        "Any publication-ready manuscript requires review by the researcher "
        "and confirmation of the methods, results, and relevant literature."
    ]

    return {
        "title": "TEMExtraction Microscopy Analysis Report",
        "run_id": str(run_id),
        "abstract": abstract,
        "methods": methods,
        "results": results,
        "discussion": discussion,
        "conclusion": conclusion,
        "limitations": limitations,
        "measurement_statistics": stats_by_measurement,
        "object_counts": object_counts,
        "image_count": image_count,
        "total_objects": total_objects,
        "units": units,
    }
