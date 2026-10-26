import sys
import os

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtCore import Qt, QEvent, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QComboBox as GraphTypeComboBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
)

from gui.report_generator_research import generate_pdf_report

class LargeImageViewer(QDialog):
    """Resizable viewer for annotated images with zoom controls."""

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Annotated Image - Large View")
        self.resize(1100, 800)
        self.original_pixmap = QPixmap(image_path)
        self.zoom_factor = 1.0

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.installEventFilter(self)
        self.image_label.setMouseTracking(True)
        self.image_label.setCursor(Qt.OpenHandCursor)
        self._drag_position = None

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.image_label)

        self.dimensions_label = QLabel()
        self.dimensions_label.setAlignment(Qt.AlignCenter)

        zoom_out = QPushButton("Zoom Out")
        zoom_in = QPushButton("Zoom In")
        actual_size = QPushButton("Actual Size")
        fit = QPushButton("Fit to Window")
        close = QPushButton("Close")

        zoom_out.clicked.connect(self.zoom_out)
        zoom_in.clicked.connect(self.zoom_in)
        actual_size.clicked.connect(self.actual_size)
        fit.clicked.connect(self.fit_to_window)
        close.clicked.connect(self.close)

        controls = QHBoxLayout()
        controls.addWidget(zoom_out)
        controls.addWidget(zoom_in)
        controls.addWidget(actual_size)
        controls.addWidget(fit)
        controls.addStretch(1)
        controls.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.dimensions_label)
        layout.addWidget(self.scroll_area, 1)
        layout.addLayout(controls)

        if self.original_pixmap.isNull():
            self.dimensions_label.setText("Could not load image.")
        else:
            self.dimensions_label.setText(
                "Image: {} × {} pixels".format(
                    self.original_pixmap.width(),
                    self.original_pixmap.height()
                )
            )
            self.fit_to_window()

    def eventFilter(self, watched, event):
        if watched is self.image_label:
            if event.type() == QEvent.Wheel:
                delta = event.angleDelta().y()
                if delta:
                    factor = 1.25 if delta > 0 else 1.0 / 1.25
                    self.zoom_at_position(event.pos(), factor)
                return True

            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._drag_position = event.globalPos()
                    self.image_label.setCursor(Qt.ClosedHandCursor)
                    return True

            elif event.type() == QEvent.MouseMove:
                if (
                    self._drag_position is not None
                    and event.buttons() & Qt.LeftButton
                ):
                    current_position = event.globalPos()
                    delta = current_position - self._drag_position
                    self.scroll_area.horizontalScrollBar().setValue(
                        self.scroll_area.horizontalScrollBar().value() - delta.x()
                    )
                    self.scroll_area.verticalScrollBar().setValue(
                        self.scroll_area.verticalScrollBar().value() - delta.y()
                    )
                    self._drag_position = current_position
                    return True

            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    self._drag_position = None
                    self.image_label.setCursor(Qt.OpenHandCursor)
                    return True

        return super().eventFilter(watched, event)

    def zoom_at_position(self, label_position, factor):
        if self.original_pixmap.isNull():
            return

        old_zoom = self.zoom_factor
        new_zoom = max(0.1, min(old_zoom * factor, 5.0))
        if new_zoom == old_zoom:
            return

        viewport = self.scroll_area.viewport()
        viewport_position = self.image_label.mapTo(
            viewport, label_position
        )

        image_x = (
            self.scroll_area.horizontalScrollBar().value()
            + viewport_position.x()
        ) / old_zoom
        image_y = (
            self.scroll_area.verticalScrollBar().value()
            + viewport_position.y()
        ) / old_zoom

        self.set_zoom(new_zoom)

        self.scroll_area.horizontalScrollBar().setValue(
            int(image_x * new_zoom - viewport_position.x())
        )
        self.scroll_area.verticalScrollBar().setValue(
            int(image_y * new_zoom - viewport_position.y())
        )

    def set_zoom(self, factor):
        if self.original_pixmap.isNull():
            return
        self.zoom_factor = max(0.1, min(factor, 5.0))
        width = max(1, int(self.original_pixmap.width() * self.zoom_factor))
        height = max(1, int(self.original_pixmap.height() * self.zoom_factor))
        scaled = self.original_pixmap.scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())

    def zoom_in(self):
        self.set_zoom(self.zoom_factor * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom_factor / 1.25)

    def actual_size(self):
        self.set_zoom(1.0)

    def fit_to_window(self):
        if self.original_pixmap.isNull():
            return
        viewport = self.scroll_area.viewport().size()
        if viewport.width() < 2 or viewport.height() < 2:
            return
        width_ratio = viewport.width() / float(self.original_pixmap.width())
        height_ratio = viewport.height() / float(self.original_pixmap.height())
        self.set_zoom(min(width_ratio, height_ratio, 1.0))


class AnalysisGraphsWidget(QWidget):
    """Display particle measurement graphs from loaded analysis results."""

    def __init__(self, size_data, parent=None, runs_root=None):
        super().__init__(parent)
        self.size_data = size_data
        self.runs_root = runs_root or os.path.join(PROJECT_ROOT, "gui_runs")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Graph type:"))

        self.graph_selector = GraphTypeComboBox()
        self.graph_selector.setMinimumWidth(300)
        self.graph_selector.setStyleSheet("""
            QComboBox {
                background-color: #201F1B;
                color: #E5DFD2;
                border: 1px solid #484133;
                border-radius: 6px;
                padding: 6px 30px 6px 9px;
                min-height: 22px;
            }
            QComboBox:hover {
                border: 1px solid #A8894B;
            }
            QComboBox:focus {
                border: 1px solid #D6B66C;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid #484133;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                background-color: #29271F;
            }
            QComboBox::down-arrow {
                image: url("gui/dropdown_arrow.svg");
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #24231F;
                color: #E5DFD2;
                border: 1px solid #61543A;
                padding: 3px;
                outline: none;
                selection-background-color: #574626;
                selection-color: #FFFFFF;
            }
        """)
        self.graph_selector.addItems([
            "Rod length distribution",
            "Rod width distribution",
            "Rod length vs. width",
            "Sphere diameter distribution",
            "Triangle height distribution",
            "Cube side-length distribution",
            "Compare rod lengths across images",
            "Compare rod lengths across saved runs",
        ])
        selector_layout.addWidget(self.graph_selector)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        self.run_selector_label = QLabel(
            "Select saved runs to compare (check the runs to include):"
        )
        layout.addWidget(self.run_selector_label)

        self.run_selector = QListWidget()
        self.run_selector.setMaximumHeight(120)
        layout.addWidget(self.run_selector)

        if os.path.isdir(self.runs_root):
            for run_name in sorted(os.listdir(self.runs_root)):
                run_dir = os.path.join(self.runs_root, run_name)
                sizes_path = os.path.join(run_dir, "sizes.json")

                if os.path.isdir(run_dir) and os.path.isfile(sizes_path):
                    item = QListWidgetItem(run_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                    self.run_selector.addItem(item)

        self.run_selector_label.hide()
        self.run_selector.hide()
        self.run_selector.itemChanged.connect(
            lambda *_: self.update_graph()
        )

        self.figure = Figure(
            figsize=(8, 5),
            facecolor="#292821",
            edgecolor="#61543A"
        )
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet(
            "background-color: #292821; border: 1px solid #484133;"
            " border-radius: 6px;"
        )
        self.canvas.setMinimumHeight(280)
        self.canvas.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        layout.addWidget(self.canvas, 1)

        self.message = QLabel("")
        layout.addWidget(self.message)

        self.statistics_table = QTableWidget()
        self.statistics_table.setAlternatingRowColors(True)
        self.statistics_table.setShowGrid(True)
        self.statistics_table.setStyleSheet("""
            QTableWidget {
                background-color: #201F1B;
                alternate-background-color: #292821;
                color: #E5DFD2;
                border: 1px solid #484133;
                gridline-color: #61543A;
                selection-background-color: #574626;
                selection-color: #FFFFFF;
            }
            QTableWidget::item {
                border: 1px solid #484133;
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #353127;
                color: #F0EBDD;
                border: 1px solid #61543A;
                padding: 6px;
                font-weight: 600;
            }
        """)
        # Keep the table's footprint stable as measurements load or clear.
        self.statistics_table.setFixedHeight(190)
        self.statistics_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.statistics_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.statistics_table.setHorizontalScrollMode(
            QTableWidget.ScrollPerPixel
        )
        self.statistics_table.setVerticalScrollMode(
            QTableWidget.ScrollPerPixel
        )
        self.statistics_table.setWordWrap(False)
        self.statistics_table.setColumnCount(9)
        self.statistics_table.setHorizontalHeaderLabels([
            "Measurement", "Count", "Mean", "Median",
            "Std. Dev.", "Minimum", "25th Percentile",
            "75th Percentile", "Maximum"
        ])
        self.statistics_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.statistics_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.statistics_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        header = self.statistics_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(90)
        header.setStretchLastSection(True)
        self.statistics_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.statistics_table.verticalHeader().setVisible(False)
        layout.addWidget(self.statistics_table)

        export_button = QPushButton("Save Graph (PNG / PDF / SVG)")
        export_button.setStyleSheet("""
            QPushButton {
                background-color: #353127;
                color: #F0EBDD;
                border: 1px solid #D6B66C;
                border-radius: 7px;
                padding: 9px 14px;
                min-height: 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #51452D;
                border: 1px solid #F0D99B;
            }
            QPushButton:pressed {
                background-color: #2D291F;
                border: 1px solid #D6B66C;
            }
            QPushButton:disabled {
                background-color: #292821;
                color: #8B8578;
                border: 1px solid #403B30;
            }
        """)
        export_button.clicked.connect(self.export_graph)
        layout.addWidget(export_button)

        self.graph_selector.currentIndexChanged.connect(
            self.update_graph
        )
        self.update_graph()

    def set_size_data(self, size_data):
        """Refresh graphs when the main window loads or clears results."""
        self.size_data = size_data or {}
        self.update_graph()

    def export_graph(self):
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Analysis Graph",
            "tem_graph.png",
            "PNG Image (*.png);;PDF Document (*.pdf);;SVG Image (*.svg)"
        )

        if not file_path:
            return

        extension = {
            "PNG Image (*.png)": ".png",
            "PDF Document (*.pdf)": ".pdf",
            "SVG Image (*.svg)": ".svg",
        }.get(selected_filter, ".png")

        current_extension = os.path.splitext(file_path)[1].lower()
        supported_extensions = (".png", ".pdf", ".svg")

        if current_extension not in supported_extensions:
            file_path += extension
        elif current_extension != extension:
            file_path = file_path[:-len(current_extension)] + extension

        try:
            self.figure.savefig(file_path, bbox_inches="tight")
            self.message.setText("Graph exported to: {}".format(file_path))
        except Exception as exc:
            self.message.setText("Graph export failed: {}".format(exc))

    def _get_all_measurements(self):
        import math

        measurements = {
            "rod_length": [],
            "rod_width": [],
            "sphere_diameter": [],
            "triangle_height": [],
            "cube_side": [],
        }
        units = set()

        paths = {
            "rod_length": ("rod", "length"),
            "rod_width": ("rod", "width"),
            "sphere_diameter": ("sphere", "diameter"),
            "triangle_height": ("triangle", "height"),
            "cube_side": ("cube", "side"),
        }

        for image_data in self.size_data.values():
            if not isinstance(image_data, dict):
                continue

            unit = image_data.get("Unit")
            if unit:
                units.add(str(unit))

            sizes = image_data.get("Size", {})
            if not isinstance(sizes, dict):
                continue

            for key, (particle, measurement) in paths.items():
                particle_data = sizes.get(particle, {})
                if not isinstance(particle_data, dict):
                    continue

                values = particle_data.get(measurement, [])
                if not isinstance(values, (list, tuple)):
                    continue

                for value in values:
                    try:
                        numeric_value = float(value)
                        if math.isfinite(numeric_value):
                            measurements[key].append(numeric_value)
                    except (TypeError, ValueError, OverflowError):
                        pass

        if len(units) > 1:
            for key in measurements:
                measurements[key] = []
            return measurements, "mixed units"

        unit_label = ", ".join(sorted(units)) if units else "unknown units"
        return measurements, unit_label

    @staticmethod
    def _calculate_statistics(values):
        import math

        finite_values = []
        for value in values:
            try:
                numeric_value = float(value)
                if math.isfinite(numeric_value):
                    finite_values.append(numeric_value)
            except (TypeError, ValueError, OverflowError):
                pass

        values = sorted(finite_values)
        count = len(values)

        if count == 0:
            return None

        mean = sum(values) / float(count)
        median = (
            values[count // 2]
            if count % 2
            else (values[count // 2 - 1] + values[count // 2]) / 2.0
        )

        if count > 1:
            variance = sum(
                (value - mean) ** 2 for value in values
            ) / float(count - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        def percentile(fraction):
            position = (count - 1) * fraction
            lower = int(math.floor(position))
            upper = int(math.ceil(position))
            if lower == upper:
                return values[lower]
            weight = position - lower
            return (
                values[lower] * (1.0 - weight)
                + values[upper] * weight
            )

        return [
            count, mean, median, std_dev, values[0],
            percentile(0.25), percentile(0.75), values[-1]
        ]

    def _update_statistics(self, measurements, unit_label):
        rows = [
            ("Rod length ({})".format(unit_label), measurements["rod_length"]),
            ("Rod width ({})".format(unit_label), measurements["rod_width"]),
            ("Sphere diameter ({})".format(unit_label), measurements["sphere_diameter"]),
            ("Triangle height ({})".format(unit_label), measurements["triangle_height"]),
            ("Cube side ({})".format(unit_label), measurements["cube_side"]),
        ]
        populated_rows = [
            (label, values, self._calculate_statistics(values))
            for label, values in rows if values
        ]

        self.statistics_table.setRowCount(len(populated_rows))

        if not populated_rows:
            self.statistics_table.clearContents()
            self.statistics_table.setRowCount(0)
            return

        for row_index, (label, values, stats) in enumerate(populated_rows):
            self.statistics_table.setItem(
                row_index, 0, QTableWidgetItem(label)
            )
            self.statistics_table.setItem(
                row_index, 1, QTableWidgetItem(str(stats[0]))
            )
            for column, value in enumerate(stats[1:], start=2):
                self.statistics_table.setItem(
                    row_index, column,
                    QTableWidgetItem("{:.3f}".format(value))
                )

    def _plot_saved_run_comparison(self, axis):
        """Compare rod-length distributions from saved runs with known units."""
        import json

        run_distributions = []
        skipped_images = 0

        if not os.path.isdir(self.runs_root):
            axis.text(
                0.5, 0.5, "Saved runs directory was not found",
                ha="center", va="center", transform=axis.transAxes
            )
            axis.set_axis_off()
            self.message.setText(
                "Could not find: {}".format(self.runs_root)
            )
            return

        selected_runs = {
            self.run_selector.item(i).text()
            for i in range(self.run_selector.count())
            if self.run_selector.item(i).checkState() == Qt.Checked
        }

        if not selected_runs:
            axis.text(
                0.5, 0.5, "Select at least one saved run to compare",
                ha="center", va="center", transform=axis.transAxes
            )
            axis.set_axis_off()
            self.message.setText("No saved runs selected.")
            return

        for run_name in sorted(os.listdir(self.runs_root)):
            if run_name not in selected_runs:
                continue

            run_dir = os.path.join(self.runs_root, run_name)
            sizes_path = os.path.join(run_dir, "sizes.json")

            if not os.path.isdir(run_dir) or not os.path.isfile(sizes_path):
                continue

            try:
                with open(sizes_path, "r") as result_file:
                    run_data = json.load(result_file)
            except (OSError, ValueError):
                continue

            if not isinstance(run_data, dict):
                continue

            unit_groups = {}

            for image_name, image_data in run_data.items():
                if not isinstance(image_data, dict):
                    continue

                unit = image_data.get("Unit")
                if not isinstance(unit, str):
                    skipped_images += 1
                    continue

                unit = unit.strip()
                if not unit or unit.lower() in ("nan", "none", "unknown", "n/a"):
                    skipped_images += 1
                    continue

                sizes = image_data.get("Size", {})
                rod_data = sizes.get("rod", {}) if isinstance(sizes, dict) else {}
                raw_lengths = (
                    rod_data.get("length", [])
                    if isinstance(rod_data, dict) else []
                )

                if not isinstance(raw_lengths, (list, tuple)):
                    continue

                values = []
                for value in raw_lengths:
                    try:
                        number = float(value)
                        if number == number and abs(number) != float("inf"):
                            values.append(number)
                    except (TypeError, ValueError):
                        continue

                if values:
                    unit_groups.setdefault(unit, []).extend(values)

            for unit, values in sorted(unit_groups.items()):
                run_distributions.append(
                    (run_name, unit, values)
                )

        if not run_distributions:
            axis.text(
                0.5, 0.5,
                "No rod-length measurements with known units were found",
                ha="center", va="center", transform=axis.transAxes,
                wrap=True
            )
            axis.set_axis_off()
            self.message.setText(
                "No comparable saved-run measurements. "
                "Images with unknown units were skipped."
            )
            return

        units = sorted(set(unit for _, unit, _ in run_distributions))
        if len(units) > 1:
            axis.text(
                0.01, 0.99,
                "Separate unit groups: {}".format(", ".join(units)),
                transform=axis.transAxes, va="top", fontsize="small"
            )

        for run_name, unit, values in run_distributions:
            axis.hist(
                values,
                bins="auto",
                alpha=0.4,
                label="{} ({}, n={})".format(run_name, unit, len(values))
            )

        axis.set_title("Rod Length Distributions Across Saved Runs")
        axis.set_xlabel("Rod length (units shown in legend)")
        axis.set_ylabel("Number of rods")
        axis.legend(fontsize="small")
        axis.grid(True, alpha=0.25)

        self.message.setText(
            "Compared {} run/unit group(s); skipped {} image(s) with "
            "unknown units.".format(len(run_distributions), skipped_images)
        )

    def update_graph(self, index=None):
        measurements, unit_label = self._get_all_measurements()
        self._update_statistics(measurements, unit_label)

        self.figure.clear()
        self.figure.set_facecolor("#292821")
        axis = self.figure.add_subplot(111)
        axis.set_facecolor("#201F1B")
        axis.tick_params(axis="both", colors="#E5DFD2", labelsize=9)
        for spine in axis.spines.values():
            spine.set_color("#8A7549")
        axis.xaxis.label.set_color("#F0EBDD")
        axis.yaxis.label.set_color("#F0EBDD")
        axis.title.set_color("#E7C979")
        graph_index = self.graph_selector.currentIndex()

        show_run_selector = graph_index == 7
        self.run_selector_label.setVisible(show_run_selector)
        self.run_selector.setVisible(show_run_selector)

        if graph_index == 7:
            self._plot_saved_run_comparison(axis)
            self.figure.tight_layout()
            self.canvas.draw()
            return

        if unit_label == "mixed units" and graph_index not in (6, 7):
            axis.text(
                0.5, 0.5,
                "Cannot combine measurements with different units.\\n"
                "Use per-image or saved-run comparison instead.",
                ha="center", va="center",
                transform=axis.transAxes, wrap=True
            )
            axis.set_axis_off()
            self.message.setText(
                "General graphs and statistics are disabled because the "
                "results contain mixed measurement units."
            )
            self.figure.tight_layout()
            self.canvas.draw()
            return

        graph_options = [
            ("rod_length", "Rod Length Distribution", "Rod length", "Number of rods"),
            ("rod_width", "Rod Width Distribution", "Rod width", "Number of rods"),
            ("rod_length", "Rod Length vs. Width", "Rod length", "Rod width"),
            ("sphere_diameter", "Sphere Diameter Distribution", "Sphere diameter", "Number of spheres"),
            ("triangle_height", "Triangle Height Distribution", "Triangle height", "Number of triangles"),
            ("cube_side", "Cube Side-Length Distribution", "Cube side length", "Number of cubes"),
        ]

        if graph_index == 6:
            import math

            image_distributions = []
            skipped_unknown_units = 0
            skipped_other_units = 0
            comparison_unit = None

            for image_name, image_data in self.size_data.items():
                if not isinstance(image_data, dict):
                    continue

                unit = image_data.get("Unit")
                if not isinstance(unit, str):
                    skipped_unknown_units += 1
                    continue

                unit = unit.strip()
                if not unit or unit.lower() in (
                    "nan", "none", "unknown", "n/a"
                ):
                    skipped_unknown_units += 1
                    continue

                sizes = image_data.get("Size", {})
                if not isinstance(sizes, dict):
                    continue

                rod_data = sizes.get("rod", {})
                if not isinstance(rod_data, dict):
                    continue

                raw_lengths = rod_data.get("length", [])
                if not isinstance(raw_lengths, (list, tuple)):
                    continue

                image_lengths = []
                for value in raw_lengths:
                    try:
                        number = float(value)
                        if math.isfinite(number):
                            image_lengths.append(number)
                    except (TypeError, ValueError):
                        continue

                if not image_lengths:
                    continue

                if comparison_unit is None:
                    comparison_unit = unit
                elif unit.lower() != comparison_unit.lower():
                    skipped_other_units += 1
                    continue

                image_distributions.append(
                    (str(image_name), image_lengths)
                )

            if len(image_distributions) < 2:
                axis.text(
                    0.5, 0.5,
                    "Need at least two images with rod lengths "
                    "in the same known unit to compare distributions",
                    ha="center", va="center",
                    transform=axis.transAxes, wrap=True
                )
                axis.set_axis_off()
                self.message.setText(
                    "Image comparison requires at least two images with "
                    "known, matching units. Skipped {} image(s) with "
                    "unknown units and {} with different units.".format(
                        skipped_unknown_units, skipped_other_units
                    )
                )
            else:
                for image_name, image_lengths in image_distributions:
                    axis.hist(
                        image_lengths,
                        bins="auto",
                        alpha=0.45,
                        label="{} (n={})".format(
                            image_name, len(image_lengths)
                        )
                    )
                axis.set_title("Rod Length Distributions Across Images")
                axis.set_xlabel(
                    "Rod length ({})".format(comparison_unit)
                )
                axis.set_ylabel("Number of rods")
                axis.legend(fontsize="small")
                axis.grid(True, alpha=0.25)
                self.message.setText(
                    "Compared {} images in {}; skipped {} image(s) "
                    "with unknown units and {} with different units.".format(
                        len(image_distributions), comparison_unit,
                        skipped_unknown_units, skipped_other_units
                    )
                )

        else:
            key, title, x_label, y_label = graph_options[graph_index]
            values = measurements[key]

        if graph_index == 6:
            pass
        elif graph_index == 2:
            lengths = measurements["rod_length"]
            widths = measurements["rod_width"]
            paired_count = min(len(lengths), len(widths))

            if paired_count == 0:
                axis.text(
                    0.5, 0.5, "No paired rod measurements available",
                    ha="center", va="center", transform=axis.transAxes
                )
                axis.set_axis_off()
            else:
                axis.scatter(
                    lengths[:paired_count],
                    widths[:paired_count],
                    color="#D6B66C",
                    edgecolors="#F0EBDD",
                    linewidths=0.45,
                    alpha=0.85
                )
                axis.set_title(title)
                axis.set_xlabel("{} ({})".format(x_label, unit_label))
                axis.set_ylabel("{} ({})".format(y_label, unit_label))
                axis.grid(True, alpha=0.25)
        elif not values:
            axis.text(
                0.5, 0.5, "No measurements available for this particle type",
                ha="center", va="center", transform=axis.transAxes
            )
            axis.set_axis_off()
        else:
            axis.hist(
                values,
                bins="auto",
                color="#C9A85C",
                edgecolor="#F0EBDD",
                linewidth=0.8,
                alpha=0.88
            )
            axis.set_title(title)
            axis.set_xlabel("{} ({})".format(x_label, unit_label))
            axis.set_ylabel(y_label)
            axis.grid(True, alpha=0.25)

        if graph_index != 6:
            self.message.setText(
                "Rods: {} lengths, {} widths | Spheres: {} diameters | "
                "Triangles: {} heights | Cubes: {} side lengths".format(
                    len(measurements["rod_length"]),
                    len(measurements["rod_width"]),
                    len(measurements["sphere_diameter"]),
                    len(measurements["triangle_height"]),
                    len(measurements["cube_side"]),
                )
            )
        self.figure.tight_layout()
        self.canvas.draw()


class AnalysisWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        output_dir,
        gpu,
        publisher,
        html_source,
        doi=None,
        year=None,
        pdf_path=None,
        manual_image=None
    ):
        super().__init__()

        self.output_dir = output_dir
        self.gpu = gpu
        self.publisher = publisher
        self.html_source = html_source
        self.doi = doi
        self.year = year
        self.pdf_path = pdf_path
        self.manual_image = manual_image

    def run(self):
        import os
        import sys
        import subprocess

        try:
            project_root = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    ".."
                )
            )

            pipeline_script = os.path.join(
                project_root,
                "pipeline_single.py"
            )

            if self.manual_image:
                command = [
                    sys.executable,
                    pipeline_script,
                    "--output_dir",
                    self.output_dir,
                    "--input_image",
                    self.manual_image,
                ]
            else:
                command = [
                    sys.executable,
                    pipeline_script,
                    "--output_dir",
                    self.output_dir,
                    "--publisher",
                    self.publisher,
                    "--html_source",
                    self.html_source,
                ]

            if self.gpu:
                command.append("--gpu")

            if self.doi:
                command.extend([
                    "--doi",
                    self.doi
                ])

            if self.year:
                command.extend([
                    "--year",
                    self.year
                ])

            if self.pdf_path:
                command.extend([
                    "--pdf_path",
                    self.pdf_path
                ])

            self.progress.emit(
                "Starting TEM extraction pipeline..."
            )

            self.progress.emit(
                "Launching pipeline process..."
            )

            self.progress.emit(
                "Command: " + " ".join(command)
            )

            pipeline_env = os.environ.copy()
            pipeline_env["MKL_THREADING_LAYER"] = "GNU"

            process = subprocess.Popen(
                command,
                cwd=project_root,
                env=pipeline_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            for line in process.stdout:
                line = line.rstrip()

                if line:
                    self.progress.emit(line)

            process.stdout.close()

            return_code = process.wait()

            if return_code != 0:
                raise RuntimeError(
                    f"Pipeline process exited with code {return_code}."
                )

            self.progress.emit(
                "Pipeline completed successfully."
            )

            self.finished.emit()

        except Exception as e:
            self.error.emit(
                f"{type(e).__name__}: {e}"
            )


class StatusLabel(QLabel):
    """Status label with theme-aware visual states."""

    def __init__(self, text="Ready", parent=None):
        super().__init__(parent)
        self.setObjectName("analysisStatus")
        self.setProperty("statusState", "ready")
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        message = str(text).strip().lower()

        if message == "ready":
            state = "ready"
        elif any(term in message for term in (
            "error", "failed", "could not", "unsupported"
        )):
            state = "error"
        elif any(term in message for term in (
            "warning", "no ", "please ", "required", "does not exist",
            "not found", "must be", "before opening graphs"
        )):
            state = "warning"
        elif any(term in message for term in (
            "starting", "running", "processing"
        )):
            state = "running"
        elif any(term in message for term in (
            "finished", "successful", "successfully", "exported",
            "results loaded"
        )):
            state = "completed"
        else:
            state = "ready"

        if self.property("statusState") != state:
            self.setProperty("statusState", state)
            style = self.style()
            style.unpolish(self)
            style.polish(self)
            self.update()


class TEMExtractionWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TEM Extraction")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 850)

        self.build_ui()

        self.worker = None
        self.current_output_dir = None
        self.annotated_images = []
        self.current_image_index = 0
        self.size_data = {}

        self.report_possible_interrupted_runs()

    def report_possible_interrupted_runs(self):
        """Report possibly interrupted runs without modifying their files."""
        import json

        runs_root = os.path.join(PROJECT_ROOT, "gui_runs")
        if not os.path.isdir(runs_root):
            return

        possible_runs = []

        for entry in sorted(os.listdir(runs_root)):
            run_dir = os.path.join(runs_root, entry)
            manifest_path = os.path.join(
                run_dir,
                "run_manifest.json"
            )

            if not os.path.isdir(run_dir):
                continue

            if not os.path.isfile(manifest_path):
                continue

            try:
                with open(manifest_path, "r") as manifest_file:
                    manifest = json.load(manifest_file)
            except (OSError, ValueError):
                continue

            if (
                isinstance(manifest, dict)
                and manifest.get("status") == "running"
            ):
                possible_runs.append((
                    entry,
                    manifest.get("started_at")
                ))

        if not possible_runs:
            return

        self.log.appendPlainText(
            "RECOVERY CHECK: Found {} run(s) still marked 'running':".format(
                len(possible_runs)
            )
        )

        for run_id, started_at in possible_runs:
            self.log.appendPlainText(
                "  - {} (started: {})".format(
                    run_id,
                    started_at or "unknown"
                )
            )

        self.log.appendPlainText(
            "These runs may be interrupted or active in another instance. "
            "No files were changed. Check each run before rerunning it."
        )

    def browse_manual_image(self):
        """Select a TEM image for manual analysis."""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TEM Image",
            "",
            "Image Files (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)"
        )

        if not file_path:
            return

        self.manual_image_path.setText(file_path)

    def update_input_mode(self, mode):
        """Switch between research paper and manual image input."""

        is_manual = mode == "Manual Image"

        self.paper_group.setVisible(not is_manual)
        self.manual_image_group.setVisible(is_manual)

    def build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setAutoFillBackground(True)
        central.setStyleSheet("background-color: #171817;")
        self.setCentralWidget(central)

        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Compact dashboard sidebar; existing analysis content stays intact.
        sidebar = QWidget()
        sidebar.setObjectName("dashboardSidebar")
        sidebar.setFixedWidth(76)
        sidebar.setStyleSheet(
            "QWidget#dashboardSidebar {"
            " background-color: #171819;"
            " border-right: 1px solid #39352B;"
            "}"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 18, 8, 16)
        sidebar_layout.setSpacing(12)

        sidebar_brand = QLabel("TEM")
        sidebar_brand.setAlignment(Qt.AlignCenter)
        sidebar_brand.setStyleSheet(
            "QLabel { color: #D6B66C; font-size: 17px;"
            " font-weight: 900; letter-spacing: 2px;"
            " padding: 8px 0 20px 0; }"
        )
        sidebar_layout.addWidget(sidebar_brand)

        self.dashboard_nav_buttons = []
        nav_items = [
            ("⚙", "Analysis Workspace"),
            ("▧", "Image & Objects"),
            ("◈", "Results & Statistics"),
            ("▤", "Data & Logs"),
        ]
        for symbol, tooltip in nav_items:
            nav_button = QPushButton(symbol)
            nav_button.setToolTip(tooltip)
            nav_button.setAccessibleName(tooltip)
            nav_button.setFixedSize(54, 48)
            nav_button.setCheckable(True)
            nav_button.setChecked(len(self.dashboard_nav_buttons) == 0)
            nav_button.setStyleSheet(
                "QPushButton { background-color: transparent;"
                " color: #A9A49A; border: 1px solid transparent;"
                " border-radius: 10px; font-size: 20px;"
                " font-weight: 600; }"
                " QPushButton:hover { background-color: #29271F;"
                " color: #E3C77F; border: 1px solid #5B4B2C; }"
                " QPushButton:checked { background-color: #39301E;"
                " color: #F0D99B; border: 1px solid #8D713A; }"
                " QPushButton:pressed { background-color: #39301E;"
                " color: #F0D99B; }"
            )
            sidebar_layout.addWidget(nav_button, 0, Qt.AlignHCenter)
            self.dashboard_nav_buttons.append(nav_button)

        sidebar_layout.addStretch()

        sidebar_mark = QLabel("●")
        sidebar_mark.setAlignment(Qt.AlignCenter)
        sidebar_mark.setStyleSheet(
            "QLabel { color: #8DAD83; font-size: 12px; padding: 8px; }"
        )
        sidebar_mark.setToolTip("TEM Extraction")
        sidebar_layout.addWidget(sidebar_mark)

        central_layout.addWidget(sidebar)

        # Main dashboard content fills the available window directly.
        # Avoid an outer scroll area around the header and workspace tabs.
        content_widget = QWidget()
        content_widget.setAutoFillBackground(True)
        content_widget.setStyleSheet("background-color: #171817;")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(18, 12, 18, 18)
        main_layout.setSpacing(14)

        central_layout.addWidget(content_widget, 1)

        # Compact dashboard header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 2, 4, 8)
        header_layout.setSpacing(12)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(3)

        title = QLabel("TEM EXTRACTION")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet(
            "QLabel { color: #F0EBDD; font-size: 22px;"
            " font-weight: 800; padding: 0; }"
        )

        subtitle = QLabel("SCIENTIFIC PARTICLE ANALYSIS  /  MICROSCOPY")
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        subtitle.setStyleSheet(
            "QLabel { color: #D6B66C; font-size: 9px;"
            " font-weight: 600; letter-spacing: 2px; padding: 0; }"
        )

        header_text_layout.addWidget(title)
        header_text_layout.addWidget(subtitle)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Analysis setup section
        setup_group = QGroupBox("Analysis Setup")
        setup_layout = QVBoxLayout(setup_group)
        setup_layout.setContentsMargins(12, 10, 12, 8)
        setup_layout.setSpacing(5)
        # Analysis Setup is hosted in its own workspace tab below.

        # Input type
        input_type_layout = QHBoxLayout()
        input_type_layout.setContentsMargins(0, 0, 0, 2)
        input_type_layout.setSpacing(10)

        input_type_label = QLabel("Input Type:")

        self.input_mode = QComboBox()
        self.input_mode.setStyleSheet(
            "QComboBox { border: 1px solid #D6B66C;"
            " background-color: #201F1B; color: #E5DFD2;"
            " padding: 7px 30px 7px 9px; min-height: 22px; }"
            " QComboBox::drop-down { width: 26px; }"
            " QComboBox::down-arrow {"
            " image: url(\"gui/dropdown_arrow.svg\");"
            " width: 12px; height: 12px; }"
        )
        self.input_mode.addItems([
            "Research Paper",
            "Manual Image",
        ])

        self.input_mode.currentTextChanged.connect(
            self.update_input_mode
        )

        input_type_label.setStyleSheet(
            "QLabel { color: #D6B66C; font-weight: 700; }"
        )
        self.input_mode.setMinimumWidth(190)
        input_type_layout.addWidget(input_type_label)
        input_type_layout.addWidget(self.input_mode, 0)
        input_type_layout.addStretch()

        setup_layout.addLayout(input_type_layout)

        # Paper information
        self.paper_group = QGroupBox("Paper Information")
        self.paper_group.setObjectName("paperInformationGroup")
        form = QFormLayout()
        form.setContentsMargins(12, 10, 12, 8)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.publisher = QComboBox()
        self.publisher.setStyleSheet(
            "QComboBox { border: 1px solid #D6B66C;"
            " background-color: #201F1B; color: #E5DFD2;"
            " padding: 7px 30px 7px 9px; min-height: 22px; }"
            " QComboBox::drop-down { width: 26px; }"
            " QComboBox::down-arrow {"
            " image: url(\"gui/dropdown_arrow.svg\");"
            " width: 12px; height: 12px; }"
        )
        self.publisher.addItems([
            "Elsevier",
            "Nature",
            "RSC",
            "Springer",
        ])

        self.html_source = QLineEdit()
        self.html_source.setStyleSheet(
                    "QLineEdit { background-color: #201F1B;"
                    " color: #E5DFD2; border: 1px solid #D6B66C;"
                    " border-radius: 6px; padding: 7px 9px;"
                    " selection-background-color: #6E592F;"
                    " selection-color: #FFFFFF; }"
                    " QLineEdit:focus { border: 2px solid #D6B66C; }"
                    " QLineEdit:disabled { color: #A19A8B;"
                    " background-color: #292821; border-color: #403B30; }"
                )
        self.html_source.setPlaceholderText(
            "Enter paper HTML source or URL"
        )

        self.doi = QLineEdit()
        self.doi.setStyleSheet(
                    "QLineEdit { background-color: #201F1B;"
                    " color: #E5DFD2; border: 1px solid #D6B66C;"
                    " border-radius: 6px; padding: 7px 9px;"
                    " selection-background-color: #6E592F;"
                    " selection-color: #FFFFFF; }"
                    " QLineEdit:focus { border: 2px solid #D6B66C; }"
                    " QLineEdit:disabled { color: #A19A8B;"
                    " background-color: #292821; border-color: #403B30; }"
                )
        self.doi.setPlaceholderText(
            "Required for Nature papers"
        )

        self.year = QLineEdit()
        self.year.setStyleSheet(
                    "QLineEdit { background-color: #201F1B;"
                    " color: #E5DFD2; border: 1px solid #D6B66C;"
                    " border-radius: 6px; padding: 7px 9px;"
                    " selection-background-color: #6E592F;"
                    " selection-color: #FFFFFF; }"
                    " QLineEdit:focus { border: 2px solid #D6B66C; }"
                    " QLineEdit:disabled { color: #A19A8B;"
                    " background-color: #292821; border-color: #403B30; }"
                )
        self.year.setPlaceholderText(
            "Required for Nature papers"
        )

        self.pdf_path = QLineEdit()
        self.pdf_path.setStyleSheet(
                    "QLineEdit { background-color: #201F1B;"
                    " color: #E5DFD2; border: 1px solid #D6B66C;"
                    " border-radius: 6px; padding: 7px 9px;"
                    " selection-background-color: #6E592F;"
                    " selection-color: #FFFFFF; }"
                    " QLineEdit:focus { border: 2px solid #D6B66C; }"
                    " QLineEdit:disabled { color: #A19A8B;"
                    " background-color: #292821; border-color: #403B30; }"
                )
        self.pdf_path.setPlaceholderText(
            "Required for Springer papers"
        )

        self.pdf_browse_button = QPushButton("Browse...")

        pdf_layout = QHBoxLayout()
        pdf_layout.addWidget(self.pdf_path)
        pdf_layout.addWidget(self.pdf_browse_button)

        pdf_widget = QWidget()
        pdf_widget.setLayout(pdf_layout)

        form.addRow("Publisher:", self.publisher)
        form.addRow("Paper HTML / URL:", self.html_source)
        form.addRow("DOI:", self.doi)
        form.addRow("Year:", self.year)

        self.pdf_label = QLabel("Article PDF:")
        form.addRow(self.pdf_label, pdf_widget)

        self.paper_group.setLayout(form)
        setup_layout.addWidget(self.paper_group)

        # Manual image input
        self.manual_image_group = QGroupBox("Manual TEM Image")
        manual_image_layout = QHBoxLayout()
        manual_image_layout.setContentsMargins(10, 14, 10, 8)
        manual_image_layout.setSpacing(10)

        self.manual_image_path = QLineEdit()
        self.manual_image_path.setStyleSheet(
                    "QLineEdit { background-color: #201F1B;"
                    " color: #E5DFD2; border: 1px solid #D6B66C;"
                    " border-radius: 6px; padding: 7px 9px;"
                    " selection-background-color: #6E592F;"
                    " selection-color: #FFFFFF; }"
                    " QLineEdit:focus { border: 2px solid #D6B66C; }"
                    " QLineEdit:disabled { color: #A19A8B;"
                    " background-color: #292821; border-color: #403B30; }"
                )
        self.manual_image_path.setReadOnly(True)
        self.manual_image_path.setPlaceholderText(
            "No image selected"
        )

        self.manual_image_browse_button = QPushButton(
            "Browse Image..."
        )
        self.manual_image_browse_button.setStyleSheet(
            "QPushButton { background-color: #353127;"
            " color: #F0EBDD; border: 1px solid #D6B66C;"
            " border-radius: 7px; padding: 9px 14px;"
            " min-height: 18px; font-weight: 600; }"
            " QPushButton:hover { background-color: #51452D;"
            " border: 1px solid #D6B66C; }"
        )

        manual_image_layout.addWidget(
            self.manual_image_path
        )
        manual_image_layout.addWidget(
            self.manual_image_browse_button
        )

        self.manual_image_group.setLayout(
            manual_image_layout
        )

        setup_layout.addWidget(
            self.manual_image_group
        )

        self.manual_image_group.setVisible(False)

        self.manual_image_browse_button.clicked.connect(
            self.browse_manual_image
        )

        # GPU option
        self.use_gpu = QCheckBox("Use GPU")
        self.use_gpu.setChecked(True)

        self.use_gpu.setStyleSheet(
            "QCheckBox { color: #D6CDBA; spacing: 8px; padding: 2px; }"
            " QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        setup_layout.addWidget(self.use_gpu)

        # Primary analysis action
        self.start_button = QPushButton("▶   START ANALYSIS")
        self.start_button.setMinimumHeight(34)
        self.start_button.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.start_button.setStyleSheet(
            "QPushButton { background-color: #9D7D3C;"
            " color: #FFFFFF; border: 1px solid #D6B66C;"
            " border-radius: 8px; padding: 10px 18px;"
            " font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #B29350; }"
            "QPushButton:pressed { background-color: #735B2C; }"
            "QPushButton:disabled { background-color: #20313F;"
            " color: #A19A8B; border-color: #484133; }"
        )
        setup_layout.addWidget(self.start_button)

        # Status
        status_title = QLabel("ANALYSIS STATUS")
        status_title.setStyleSheet(
            "QLabel { color: #A9A49A; font-size: 9px;"
            " font-weight: 700; letter-spacing: 1px; }"
        )
        setup_layout.addWidget(status_title)

        self.status = StatusLabel("Ready")
        setup_layout.addWidget(self.status)

        self.progress_indicator = QProgressBar()
        self.progress_indicator.setObjectName("analysisProgress")
        self.progress_indicator.setRange(0, 0)
        self.progress_indicator.setTextVisible(False)
        self.progress_indicator.setFixedHeight(7)
        self.progress_indicator.hide()
        setup_layout.addWidget(self.progress_indicator)

        # Workspace tabs. Existing analysis widgets are reused.
        results_tabs = QTabWidget()
        results_tabs.setObjectName("workspaceTabs")
        main_layout.addWidget(results_tabs, 1)

        setup_tab = QWidget()
        setup_tab_layout = QVBoxLayout(setup_tab)
        setup_tab_layout.setContentsMargins(12, 12, 12, 12)
        setup_tab_layout.addWidget(setup_group)

        # About and Quick Start guide for first-time users.
        help_panel = QGroupBox("About TEMExtraction  |  QUICK START")
        help_panel.setObjectName("aboutQuickStartPanel")
        help_panel.setStyleSheet(
            "QGroupBox#aboutQuickStartPanel {"
            " color: #D6B66C; font-size: 12px; font-weight: 700;"
            " border: 1px solid #484133; border-radius: 9px;"
            " margin-top: 10px; padding: 10px;"
            " background-color: #201F1B; }"
            "QGroupBox#aboutQuickStartPanel::title {"
            " subcontrol-origin: margin; left: 12px;"
            " padding: 0 6px; }"
        )
        help_layout = QVBoxLayout(help_panel)
        help_layout.setContentsMargins(12, 10, 12, 8)
        help_layout.setSpacing(7)

        about_text = QLabel(
            "TEMExtraction helps researchers extract microscopy figures "
            "from supported research-paper sources or analyze a manually "
            "selected TEM image, then review detected objects and "
            "particle measurements."
        )
        about_text.setWordWrap(True)
        about_text.setStyleSheet(
            "QLabel { color: #E5DFD2; font-size: 13px;"
            " font-weight: 400; background: transparent; }"
        )
        help_layout.addWidget(about_text)

        quick_start_title = QLabel("HOW TO USE")
        quick_start_title.setStyleSheet(
            "QLabel { color: #D6B66C; font-size: 10px;"
            " font-weight: 800; letter-spacing: 1px;"
            " background: transparent; }"
        )
        help_layout.addWidget(quick_start_title)

        quick_start_text = QLabel(
            "1. Choose Research Paper or Manual Image.\n"
            "2. Enter the required paper details or browse for an image.\n"
            "3. Keep Use GPU enabled if your system supports it.\n"
            "4. Select START ANALYSIS and monitor Analysis Status.\n"
            "5. Review images, objects, results, charts, and logs in the "
            "other workspaces. Use Data & Logs to export available results."
        )
        quick_start_text.setWordWrap(True)
        quick_start_text.setStyleSheet(
            "QLabel { color: #C9C2B4; font-size: 13px;"
            " font-weight: 400; line-height: 1.3;"
            " background: transparent; }"
        )
        help_layout.addWidget(quick_start_text)

        setup_tab_layout.addWidget(help_panel)
        setup_tab_layout.addStretch()
        results_tabs.addTab(setup_tab, "Analysis Workspace")

        image_tab = QWidget()
        image_layout = QVBoxLayout(image_tab)
        image_layout.setContentsMargins(12, 12, 12, 12)
        image_layout.setSpacing(10)

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(12, 12, 12, 12)
        overview_layout.setSpacing(12)

        objects_tab = QWidget()
        objects_layout = QVBoxLayout(objects_tab)
        objects_layout.setContentsMargins(12, 12, 12, 12)
        objects_layout.setSpacing(10)

        charts_tab = QWidget()
        charts_layout = QVBoxLayout(charts_tab)
        charts_layout.setContentsMargins(12, 12, 12, 12)
        charts_layout.setSpacing(12)

        charts_title = QLabel("Analysis Charts")
        charts_title.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: 700; padding: 4px; }"
        )

        charts_description = QLabel(
            "Visualize particle measurements, compare distributions, "
            "and review statistics from your loaded analysis results."
        )
        charts_description.setWordWrap(True)

        charts_panel = QFrame()
        charts_panel.setObjectName("chartsPanel")
        charts_panel.setStyleSheet(
            "QFrame#chartsPanel { background-color: #292821;"
            " border: 1px solid #484133; border-radius: 8px; }"
        )
        charts_panel_layout = QVBoxLayout(charts_panel)
        charts_panel_layout.setContentsMargins(16, 16, 16, 16)
        charts_panel_layout.setSpacing(8)

        charts_panel_title = QLabel("Particle Measurement Graphs")
        charts_panel_title.setStyleSheet(
            "QLabel { font-size: 14px; font-weight: 600;"
            " border: none; background: transparent; }"
        )

        charts_panel_description = QLabel(
            "Explore particle distributions, compare images or saved runs, "
            "review statistics, and export graphs as PNG, PDF, or SVG."
        )
        charts_panel_description.setWordWrap(True)
        charts_panel_description.setStyleSheet(
            "QLabel { border: none; background: transparent; }"
        )

        charts_layout.addWidget(charts_title)
        charts_layout.addWidget(charts_description)
        charts_panel_layout.addWidget(charts_panel_title)
        charts_panel_layout.addWidget(charts_panel_description)

        self.analysis_graphs_widget = AnalysisGraphsWidget(
            {},
            self,
            os.path.join(PROJECT_ROOT, "gui_runs")
        )
        # Reserve enough vertical space for the graph, statistics
        # table, selector, message, and export button.
        self.analysis_graphs_widget.setMinimumHeight(660)
        charts_panel_layout.addWidget(self.analysis_graphs_widget)
        charts_layout.addWidget(charts_panel, 1)

        spreadsheet_tab = QWidget()
        spreadsheet_layout = QVBoxLayout(spreadsheet_tab)
        spreadsheet_layout.setContentsMargins(12, 12, 12, 12)
        spreadsheet_layout.setSpacing(10)

        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(12, 12, 12, 12)
        logs_layout.setSpacing(10)

        # Sidebar buttons navigate the existing result tabs.
        def sync_dashboard_navigation(index):
            for button_index, button in enumerate(self.dashboard_nav_buttons):
                button.setChecked(button_index == index)

        for index, nav_button in enumerate(self.dashboard_nav_buttons):
            nav_button.clicked.connect(
                lambda checked=False, tab_index=index:
                    results_tabs.setCurrentIndex(tab_index)
            )

        results_tabs.currentChanged.connect(sync_dashboard_navigation)

        # Scientific dashboard: compact metric cards
        summary_layout = QHBoxLayout()
        summary_layout.setContentsMargins(0, 4, 0, 8)
        summary_layout.setSpacing(10)

        self.images_summary = QLabel("Images\n0")
        self.objects_summary = QLabel("Objects\n0")
        self.rods_summary = QLabel("Rods\n0")
        self.spheres_summary = QLabel("Spheres\n0")
        self.cubes_summary = QLabel("Cubes\n0")
        self.triangles_summary = QLabel("Triangles\n0")
        self.scaled_summary = QLabel("Images with scale\n0")

        for widget in [
            self.images_summary,
            self.objects_summary,
            self.rods_summary,
            self.spheres_summary,
            self.cubes_summary,
            self.triangles_summary,
            self.scaled_summary,
        ]:
            widget.setAlignment(Qt.AlignCenter)
            widget.setMinimumHeight(94)
            widget.setMinimumWidth(86)
            widget.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Fixed
            )
            widget.setWordWrap(True)
            widget.setStyleSheet(
                "QLabel {"
                " background-color: #24231F;"
                " color: #E7D7AD;"
                " border: 1px solid #51452D;"
                " border-top: 3px solid #D6B66C;"
                " border-radius: 8px;"
                " padding: 11px 6px;"
                " font-size: 12px;"
                " font-weight: 700;"
                "}"
            )
            summary_layout.addWidget(widget, 1)

        overview_layout.addLayout(summary_layout)

        # Titled results panel; retain the existing results widget and handlers.
        results_panel = QGroupBox("RESULTS SUMMARY")
        results_panel.setObjectName("overviewResultsPanel")
        results_panel_layout = QVBoxLayout(results_panel)
        results_panel_layout.setContentsMargins(10, 10, 10, 8)
        results_panel_layout.setSpacing(6)

        results_hint = QLabel(
            "Detection report  /  Object counts and analysis details"
        )
        results_hint.setObjectName("overviewResultsHint")
        results_hint.setStyleSheet(
            "QLabel { color: #A9A18F; font-size: 9pt; padding: 0 2px; }"
        )
        results_panel_layout.addWidget(results_hint)

        self.results = QPlainTextEdit()
        self.results.setObjectName("overviewResultsText")
        self.results.setReadOnly(True)
        self.results.setMinimumHeight(180)
        self.results.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.results.setPlaceholderText(
            "Your analysis report will appear here after a successful run."
        )
        results_panel_layout.addWidget(self.results)
        overview_layout.addWidget(results_panel, 1)

        # Annotated image preview
        image_title = QLabel("Annotated TEM Image")
        image_layout.addWidget(image_title)

        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumSize(0, 300)
        self.image_preview.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.image_preview.setStyleSheet(
            "QLabel { background-color: #111210;"
            " color: #8F8B80; border: 1px solid #39352B;"
            " border-radius: 10px; padding: 12px; }"
        )
        self.image_preview.setText(
            "Annotated images will appear here after loading results."
        )
        image_layout.addWidget(self.image_preview)

        self.image_filename = QLabel("")
        self.image_filename.setAlignment(Qt.AlignCenter)
        image_layout.addWidget(self.image_filename)

        self.image_details = QPlainTextEdit()
        self.image_details.setReadOnly(True)
        self.image_details.setMinimumHeight(64)
        self.image_details.setMaximumHeight(105)
        self.image_details.setPlaceholderText(
            "Measurements for the selected image will appear here."
        )
        image_layout.addWidget(self.image_details)

        # Image navigation
        image_navigation = QHBoxLayout()

        self.previous_image_button = QPushButton("Previous Image")
        self.previous_image_button.setEnabled(False)

        self.image_counter = QLabel("Image 0 of 0")
        self.image_counter.setAlignment(Qt.AlignCenter)

        self.next_image_button = QPushButton("Next Image")
        self.next_image_button.setEnabled(False)

        self.view_large_image_button = QPushButton("View Large Image")
        self.view_large_image_button.setEnabled(False)

        image_navigation.addWidget(self.previous_image_button)
        image_navigation.addWidget(self.image_counter)
        image_navigation.addWidget(self.next_image_button)
        image_navigation.addWidget(self.view_large_image_button)

        image_layout.addLayout(image_navigation)

        self.object_table = QTableWidget()
        self.object_table.setColumnCount(2)
        self.object_table.setHorizontalHeaderLabels([
            "Object",
            "Detected",
        ])
        self.object_table.setAlternatingRowColors(True)
        self.object_table.setShowGrid(True)
        self.object_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #484133;
                gridline-color: #61543A;
            }
            QTableWidget::item {
                border: 1px solid #484133;
                padding: 4px;
            }
        """)
        self.object_table.setMinimumHeight(220)
        self.object_table.setWordWrap(False)
        self.object_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.object_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.object_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.object_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.object_table.setSelectionMode(
            QTableWidget.SingleSelection
        )
        self.object_table.verticalHeader().setVisible(False)
        self.object_table.verticalHeader().setDefaultSectionSize(34)
        self.object_table.horizontalHeader().setMinimumHeight(34)
        self.object_table.horizontalHeader().setStretchLastSection(True)
        self.object_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.object_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        objects_layout.addWidget(self.object_table, 1)

        # Measurement details and table share the available workspace.
        spreadsheet_content = QHBoxLayout()
        spreadsheet_content.setContentsMargins(0, 0, 0, 0)
        spreadsheet_content.setSpacing(12)

        self.measurement_details_panel = QGroupBox("MEASUREMENT DETAILS")
        self.measurement_details_panel.setObjectName(
            "measurementDetailsPanel"
        )
        self.measurement_details_panel.setMinimumWidth(210)
        self.measurement_details_panel.setMaximumWidth(290)
        details_layout = QVBoxLayout(self.measurement_details_panel)
        details_layout.setContentsMargins(14, 16, 14, 14)
        details_layout.setSpacing(10)

        self.measurement_detail_name = QLabel("No measurement selected")
        self.measurement_detail_name.setWordWrap(True)
        self.measurement_detail_name.setStyleSheet(
            "QLabel { color: #E7D7AD; font-size: 14px; "
            "font-weight: 700; padding: 4px 0; }"
        )
        details_layout.addWidget(self.measurement_detail_name)

        self.measurement_detail_count = QLabel("Count\n—")
        self.measurement_detail_min = QLabel("Minimum\n—")
        self.measurement_detail_max = QLabel("Maximum\n—")
        self.measurement_detail_average = QLabel("Average\n—")

        for detail_label in (
            self.measurement_detail_count,
            self.measurement_detail_min,
            self.measurement_detail_max,
            self.measurement_detail_average,
        ):
            detail_label.setWordWrap(True)
            detail_label.setStyleSheet(
                "QLabel { color: #D6CDBA; background-color: #24231F; "
                "border: 1px solid #484133; border-radius: 6px; "
                "padding: 9px; }"
            )
            details_layout.addWidget(detail_label)

        details_layout.addStretch()

        self.measurement_table = QTableWidget()
        self.measurement_table.setColumnCount(5)
        self.measurement_table.setHorizontalHeaderLabels([
            "Measurement",
            "Count",
            "Min",
            "Max",
            "Average",
        ])
        self.measurement_table.setAlternatingRowColors(True)
        self.measurement_table.setShowGrid(True)
        self.measurement_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #484133;
                gridline-color: #61543A;
            }
            QTableWidget::item {
                border: 1px solid #484133;
                padding: 4px;
            }
        """)
        self.measurement_table.setMinimumHeight(220)
        self.measurement_table.setWordWrap(False)
        self.measurement_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.measurement_table.verticalHeader().setDefaultSectionSize(34)
        self.measurement_table.horizontalHeader().setMinimumHeight(34)
        self.measurement_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.measurement_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.measurement_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.measurement_table.verticalHeader().setVisible(False)
        spreadsheet_content.addWidget(
            self.measurement_details_panel, 0
        )
        spreadsheet_content.addWidget(self.measurement_table, 1)
        spreadsheet_layout.addLayout(spreadsheet_content, 1)

        self.measurement_table.itemSelectionChanged.connect(
            self.update_measurement_details
        )

        spreadsheet_actions = QHBoxLayout()
        spreadsheet_actions.setSpacing(8)

        self.load_results_button = QPushButton("Load Previous Results")
        self.load_results_button.setStyleSheet(
            "QPushButton { background-color: #353127;"
            " color: #F0EBDD; border: 1px solid #D6B66C;"
            " border-radius: 7px; padding: 9px 14px;"
            " min-height: 18px; font-weight: 600; }"
            " QPushButton:hover { background-color: #51452D;"
            " border: 1px solid #D6B66C; }"
            " QPushButton:pressed { background-color: #2D291F;"
            " border: 1px solid #D6B66C; }"
            " QPushButton:disabled { background-color: #292821;"
            " color: #8B8578; border: 1px solid #403B30; }"
        )
        spreadsheet_actions.addWidget(self.load_results_button)

        self.export_results_button = QPushButton("Export Results")
        self.export_results_button.setEnabled(False)
        spreadsheet_actions.addWidget(self.export_results_button)

        self.export_detailed_button = QPushButton("Export Detailed CSV")
        self.export_detailed_button.setEnabled(False)
        spreadsheet_actions.addWidget(self.export_detailed_button)

        self.export_metadata_button = QPushButton("Export Metadata JSON")
        self.export_metadata_button.setEnabled(False)
        spreadsheet_actions.addWidget(self.export_metadata_button)

        self.export_pdf_button = QPushButton("Generate PDF Report")
        self.export_pdf_button.setEnabled(False)
        spreadsheet_actions.addWidget(self.export_pdf_button)
        spreadsheet_layout.addLayout(spreadsheet_actions)



        # Analysis Log
        log_title = QLabel("Analysis Log")
        logs_layout.addWidget(log_title)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        logs_layout.addWidget(self.log)

        # Combine existing pages into four adjustable workspaces.
        # Reuse the original page widgets and their existing handlers.

        image_objects_splitter = QSplitter(Qt.Horizontal)
        image_objects_splitter.setObjectName("imageObjectsSplitter")
        image_objects_splitter.setChildrenCollapsible(False)
        image_objects_splitter.addWidget(image_tab)
        image_objects_splitter.addWidget(objects_tab)
        image_objects_splitter.setStretchFactor(0, 3)
        image_objects_splitter.setStretchFactor(1, 2)
        image_objects_splitter.setSizes([650, 400])
        results_tabs.addTab(image_objects_splitter, "Image && Objects")

        results_statistics_splitter = QSplitter(Qt.Vertical)
        results_statistics_splitter.setObjectName(
            "resultsStatisticsSplitter"
        )
        results_statistics_splitter.setChildrenCollapsible(False)
        results_statistics_splitter.addWidget(overview_tab)
        results_statistics_splitter.addWidget(charts_tab)
        results_statistics_splitter.setStretchFactor(0, 1)
        results_statistics_splitter.setStretchFactor(1, 2)
        results_statistics_splitter.setSizes([340, 620])

        # Keep the complete overview and charts accessible in a
        # dedicated scroll area when the maximized window is too short.
        results_statistics_splitter.setMinimumHeight(1650)

        results_statistics_scroll = QScrollArea()
        results_statistics_scroll.setObjectName(
            "resultsStatisticsScrollArea"
        )
        results_statistics_scroll.setWidgetResizable(True)
        results_statistics_scroll.setFrameShape(QFrame.NoFrame)
        results_statistics_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        results_statistics_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        results_statistics_content = QWidget()
        results_statistics_layout = QVBoxLayout(
            results_statistics_content
        )
        results_statistics_layout.setContentsMargins(0, 0, 0, 0)
        results_statistics_layout.setSpacing(0)
        results_statistics_layout.addWidget(results_statistics_splitter)

        results_statistics_scroll.setWidget(
            results_statistics_content
        )
        results_tabs.addTab(
            results_statistics_scroll, "Results && Statistics"
        )

        data_logs_splitter = QSplitter(Qt.Horizontal)
        data_logs_splitter.setObjectName("dataLogsSplitter")
        data_logs_splitter.setChildrenCollapsible(False)
        data_logs_splitter.addWidget(spreadsheet_tab)
        data_logs_splitter.addWidget(logs_tab)
        data_logs_splitter.setStretchFactor(0, 3)
        data_logs_splitter.setStretchFactor(1, 1)
        data_logs_splitter.setSizes([760, 320])
        results_tabs.addTab(data_logs_splitter, "Data && Logs")


        # Publisher behavior
        self.publisher.currentTextChanged.connect(
            self.update_publisher_fields
        )

        # Set initial state
        self.update_publisher_fields(
            self.publisher.currentText()
        )

        self.pdf_browse_button.clicked.connect(
            self.browse_pdf
        )

        self.start_button.clicked.connect(
            self.start_analysis
        )

        self.load_results_button.clicked.connect(
            self.load_previous_results
        )

        self.export_results_button.clicked.connect(
            self.export_results
        )

        self.export_detailed_button.clicked.connect(
            self.export_detailed_results
        )

        self.export_metadata_button.clicked.connect(
            self.export_analysis_metadata
        )

        self.export_pdf_button.clicked.connect(
            self.export_pdf_report
        )

        # Apply consistent idle-state borders to regular action buttons.
        regular_buttons = (
            self.pdf_browse_button,
            self.previous_image_button,
            self.next_image_button,
            self.view_large_image_button,
            self.export_results_button,
            self.export_detailed_button,
            self.export_metadata_button,
            self.export_pdf_button,
        )

        for button in regular_buttons:
            button.setStyleSheet(
                "QPushButton { background-color: #353127;"
                " color: #F0EBDD; border: 1px solid #D6B66C;"
                " border-radius: 7px; padding: 9px 14px;"
                " min-height: 18px; font-weight: 600; }"
                " QPushButton:hover { background-color: #51452D;"
                " border: 1px solid #D6B66C; }"
                " QPushButton:pressed { background-color: #2D291F;"
                " border: 1px solid #D6B66C; }"
                " QPushButton:disabled { background-color: #292821;"
                " color: #8B8578; border: 1px solid #403B30; }"
            )

        self.previous_image_button.clicked.connect(
            self.show_previous_image
        )

        self.next_image_button.clicked.connect(
            self.show_next_image
        )

        self.view_large_image_button.clicked.connect(
            self.open_large_image
        )

    def update_measurement_details(self):
        """Show the values from the currently selected measurement row."""
        row = self.measurement_table.currentRow()

        if row < 0:
            self.measurement_detail_name.setText(
                "No measurement selected"
            )
            self.measurement_detail_count.setText("Count\n—")
            self.measurement_detail_min.setText("Minimum\n—")
            self.measurement_detail_max.setText("Maximum\n—")
            self.measurement_detail_average.setText("Average\n—")
            return

        items = [
            self.measurement_table.item(row, column)
            for column in range(5)
        ]
        values = [
            item.text() if item is not None else "—"
            for item in items
        ]

        self.measurement_detail_name.setText(values[0])
        self.measurement_detail_count.setText(
            "Count\n{}".format(values[1])
        )
        self.measurement_detail_min.setText(
            "Minimum\n{}".format(values[2])
        )
        self.measurement_detail_max.setText(
            "Maximum\n{}".format(values[3])
        )
        self.measurement_detail_average.setText(
            "Average\n{}".format(values[4])
        )

    def load_previous_results(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Previous Analysis Folder",
            ""
        )

        if not folder:
            return

        self.current_output_dir = folder
        self.load_analysis_results()

        result_message = self.results.toPlainText()
        if result_message.startswith("Could not read analysis results."):
            self.status.setText(
                "Status: Previous results could not be loaded."
            )
        elif "sizes.json was not found." in result_message:
            self.status.setText(
                "Status: Folder selected, but no sizes.json was found."
            )
        else:
            self.status.setText(
                "Status: Previous results loaded."
            )

    def export_pdf_report(self):
        if not self.current_output_dir or not self.size_data:
            self.status.setText(
                "Status: No analysis data available for a PDF report."
            )
            return

        default_path = os.path.join(
            self.current_output_dir,
            "tem_extraction_report.pdf"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Generate PDF Analysis Report",
            default_path,
            "PDF files (*.pdf)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        try:
            output_path = generate_pdf_report(
                self.current_output_dir,
                file_path
            )
            self.status.setText(
                "Status: PDF report saved to {}".format(output_path)
            )
            self.log.appendPlainText(
                "PDF report generated: {}".format(output_path)
            )
            QMessageBox.information(
                self,
                "PDF Report Generated",
                "The analysis report was saved successfully to:\n{}".format(
                    output_path
                )
            )
        except Exception as e:
            self.status.setText(
                "Status: Could not generate PDF report: {}".format(e)
            )
            self.log.appendPlainText(
                "PDF report error: {}: {}".format(type(e).__name__, e)
            )
            QMessageBox.warning(
                self,
                "PDF Report Error",
                "Could not generate the PDF report:\n{}".format(e)
            )

    def export_results(self):
        if not self.current_output_dir:
            self.status.setText(
                "Status: No analysis results available to export."
            )
            return

        if self.measurement_table.rowCount() == 0:
            self.status.setText(
                "Status: No measurement results available to export."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Analysis Results",
            os.path.join(
                self.current_output_dir,
                "analysis_results.csv"
            ),
            "CSV files (*.csv)"
        )

        if not file_path:
            return

        try:
            import csv

            with open(file_path, "w", newline="") as csv_file:
                writer = csv.writer(csv_file)

                writer.writerow([
                    "Measurement",
                    "Count",
                    "Min",
                    "Max",
                    "Average",
                    "Unit",
                ])

                units = set()
                has_unknown_units = False

                for image_data in self.size_data.values():
                    if not isinstance(image_data, dict):
                        has_unknown_units = True
                        continue

                    unit = image_data.get("Unit")

                    if (
                        isinstance(unit, str)
                        and unit.strip()
                        and unit.strip().lower() not in (
                            "none", "nan", "unknown"
                        )
                    ):
                        units.add(unit.strip())
                    else:
                        has_unknown_units = True

                if len(units) > 1:
                    unit_text = "Mixed units"
                elif has_unknown_units and units:
                    unit_text = "Mixed/unknown units"
                elif has_unknown_units:
                    unit_text = "Unknown units"
                elif units:
                    unit_text = sorted(units)[0]
                else:
                    unit_text = "Unknown units"

                for row in range(self.measurement_table.rowCount()):
                    values = []

                    for column in range(5):
                        item = self.measurement_table.item(row, column)
                        values.append(
                            item.text() if item else ""
                        )

                    writer.writerow(values + [unit_text])

            self.status.setText(
                "Status: Results exported successfully."
            )

        except Exception as e:
            self.status.setText(
                "Status: Could not export results: {}".format(e)
            )

    def export_detailed_results(self):
        if not self.current_output_dir or not self.size_data:
            self.status.setText(
                "Status: No analysis data available to export."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Detailed Measurements",
            os.path.join(
                self.current_output_dir,
                "detailed_measurements.csv"
            ),
            "CSV files (*.csv)"
        )

        if not file_path:
            return

        try:
            import csv
            import math

            measurement_keys = [
                ("rod", "length", "Rod", "Length"),
                ("rod", "width", "Rod", "Width"),
                ("sphere", "diameter", "Sphere", "Diameter"),
                ("triangle", "height", "Triangle", "Height"),
                ("cube", "side", "Cube", "Side"),
            ]

            exported_count = 0

            with open(file_path, "w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow([
                    "Image",
                    "Object Type",
                    "Measurement Type",
                    "Object Index",
                    "Value",
                    "Unit",
                ])

                for image_name, image_data in self.size_data.items():
                    if not isinstance(image_data, dict):
                        continue

                    unit = image_data.get("Unit")
                    if (
                        not isinstance(unit, str)
                        or not unit.strip()
                        or unit.strip().lower() in (
                            "none", "nan", "unknown"
                        )
                    ):
                        unit = "Unknown units"
                    else:
                        unit = unit.strip()

                    size_groups = image_data.get("Size", {})

                    for group, key, object_name, measurement_name in measurement_keys:
                        values = size_groups.get(group, {}).get(key, [])

                        if not isinstance(values, list):
                            continue

                        for index, value in enumerate(values, start=1):
                            try:
                                numeric_value = float(value)
                            except (TypeError, ValueError):
                                continue

                            if not math.isfinite(numeric_value):
                                continue

                            writer.writerow([
                                image_name,
                                object_name,
                                measurement_name,
                                index,
                                numeric_value,
                                unit,
                            ])
                            exported_count += 1

            self.status.setText(
                "Status: Exported {} individual measurements.".format(
                    exported_count
                )
            )

        except Exception as e:
            self.status.setText(
                "Status: Could not export detailed results: {}".format(e)
            )

    def export_analysis_metadata(self):
        if not self.current_output_dir or not self.size_data:
            self.status.setText(
                "Status: No analysis data available to export."
            )
            return

        try:
            import json
            import math
            import os
            import statistics
            from datetime import datetime

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Analysis Metadata",
                os.path.join(
                    self.current_output_dir,
                    "analysis_metadata.json"
                ),
                "JSON files (*.json)"
            )

            if not file_path:
                return

            measurement_keys = [
                ("rod", "length", "Rod length"),
                ("rod", "width", "Rod width"),
                ("sphere", "diameter", "Sphere diameter"),
                ("triangle", "height", "Triangle height"),
                ("cube", "side", "Cube side"),
            ]

            object_counts = {
                "rods": 0,
                "spheres": 0,
                "triangles": 0,
                "cubes": 0,
            }
            measurement_values = {
                label: [] for _, _, label in measurement_keys
            }
            image_metadata = []
            missing_unit_images = []
            invalid_values = 0
            units = set()

            for image_name, image_data in self.size_data.items():
                if not isinstance(image_data, dict):
                    missing_unit_images.append(image_name)
                    continue

                size_groups = image_data.get("Size", {})
                raw_unit = image_data.get("Unit")
                unit = (
                    raw_unit.strip()
                    if isinstance(raw_unit, str)
                    else ""
                )

                if (
                    not unit
                    or unit.lower() in ("none", "nan", "unknown")
                ):
                    missing_unit_images.append(image_name)
                    unit = None
                else:
                    units.add(unit)

                image_counts = {
                    "rods": 0,
                    "spheres": 0,
                    "triangles": 0,
                    "cubes": 0,
                }

                object_group_names = {
                    "rod": "rods",
                    "sphere": "spheres",
                    "triangle": "triangles",
                    "cube": "cubes",
                }

                for group, count_name in object_group_names.items():
                    group_data = size_groups.get(group, {})
                    if not isinstance(group_data, dict):
                        continue

                    count_key = {
                        "rod": "length",
                        "sphere": "diameter",
                        "triangle": "height",
                        "cube": "side",
                    }[group]

                    values = group_data.get(count_key, [])
                    if isinstance(values, list):
                        image_counts[count_name] = len(values)
                        object_counts[count_name] += len(values)

                for group, key, label in measurement_keys:
                    group_data = size_groups.get(group, {})
                    values = (
                        group_data.get(key, [])
                        if isinstance(group_data, dict)
                        else []
                    )

                    if not isinstance(values, list):
                        continue

                    for value in values:
                        try:
                            number = float(value)
                        except (TypeError, ValueError):
                            invalid_values += 1
                            continue

                        if not math.isfinite(number):
                            invalid_values += 1
                            continue

                        measurement_values[label].append(number)

                image_metadata.append({
                    "image": image_name,
                    "unit": unit,
                    "object_counts": image_counts,
                })

            measurement_statistics = {}

            for label, values in measurement_values.items():
                if not values:
                    measurement_statistics[label] = {
                        "count": 0,
                        "min": None,
                        "max": None,
                        "mean": None,
                        "median": None,
                        "standard_deviation": None,
                    }
                    continue

                measurement_statistics[label] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.mean(values),
                    "median": statistics.median(values),
                    "standard_deviation": (
                        statistics.stdev(values)
                        if len(values) > 1
                        else 0.0
                    ),
                }

            metadata = {
                "metadata_format_version": 1,
                "generated_at": datetime.now().isoformat(),
                "output_directory": os.path.abspath(
                    self.current_output_dir
                ),
                "source_file": "sizes.json",
                "images_analyzed": len(self.size_data),
                "total_objects": sum(object_counts.values()),
                "object_counts": object_counts,
                "units_found": sorted(units),
                "images_with_missing_unit": missing_unit_images,
                "per_image": image_metadata,
                "measurement_statistics": measurement_statistics,
                "data_quality": {
                    "invalid_or_non_finite_measurements_skipped": invalid_values,
                    "note": (
                        "Statistics combine numeric values as stored in "
                        "sizes.json. If images use different units, "
                        "statistics may combine incomparable measurements."
                    ),
                },
            }

            with open(file_path, "w") as output_file:
                json.dump(metadata, output_file, indent=2, allow_nan=False)
                output_file.write("\n")

            self.status.setText(
                "Status: Analysis metadata exported successfully."
            )

        except Exception as e:
            self.status.setText(
                "Status: Could not export metadata: {}".format(e)
            )

    def browse_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Article PDF",
            "",
            "PDF files (*.pdf)"
        )

        if file_path:
            self.pdf_path.setText(file_path)
    
    def validate_inputs(self):
        input_mode = self.input_mode.currentText()

        if input_mode == "Manual Image":
            image_path = self.manual_image_path.text().strip()

            if not image_path:
                self.status.setText(
                    "Status: Please select a TEM image."
                )
                return False

            if not os.path.isfile(image_path):
                self.status.setText(
                    "Status: Selected TEM image does not exist."
                )
                return False

            supported_extensions = (
                ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"
            )
            image_extension = os.path.splitext(image_path)[1].lower()

            if image_extension not in supported_extensions:
                self.status.setText(
                    "Status: Unsupported image format. "
                    "Use JPG, JPEG, PNG, TIF, TIFF, or BMP."
                )
                return False

            try:
                from PIL import Image

                with Image.open(image_path) as image:
                    image.verify()
            except Exception as error:
                self.status.setText(
                    "Status: Selected file is not a readable image "
                    "({}).".format(error)
                )
                return False

            image_name = os.path.basename(image_path).lower()
            looks_annotated = (
                ".annotated." in image_name
                or image_name.endswith("_annotated")
                or "_annotated." in image_name
            )

            if looks_annotated:
                answer = QMessageBox.warning(
                    self,
                    "Possibly Annotated Image",
                    "This filename looks like an annotated output image. "
                    "For reliable classification and measurements, select "
                    "the original, unannotated TEM image instead.\n\n"
                    "Do you want to continue with this image anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if answer != QMessageBox.Yes:
                    self.status.setText(
                        "Status: Please select the original TEM image."
                    )
                    return False

            self.status.setText(
                "Status: Manual image validation successful."
            )
            return True

        publisher = self.publisher.currentText()
        html_source = self.html_source.text().strip()
        doi = self.doi.text().strip()
        year = self.year.text().strip()
        pdf_path = self.pdf_path.text().strip()

        if not html_source:
            self.status.setText(
                "Status: Please enter a paper HTML / URL."
            )
            return False

        if publisher == "Springer":
            if not pdf_path:
                self.status.setText(
                    "Status: Article PDF is required for Springer papers."
                )
                return False

            if not os.path.isfile(pdf_path):
                self.status.setText(
                    "Status: Selected Springer PDF does not exist."
                )
                return False

        if publisher == "Nature":
            if not doi:
                self.status.setText(
                    "Status: DOI is required for Nature papers."
                )
                return False

            if not year:
                self.status.setText(
                    "Status: Year is required for Nature papers."
                )
                return False

            if not year.isdigit():
                self.status.setText(
                    "Status: Year must be a number."
                )
                return False

        self.status.setText("Status: Input validation successful.")
        return True

    def update_publisher_fields(self, publisher):
        is_nature = publisher == "Nature"
        is_springer = publisher == "Springer"

        self.doi.setVisible(is_nature)
        self.year.setVisible(is_nature)
        self.pdf_path.setVisible(is_springer)
        self.pdf_browse_button.setVisible(is_springer)
        self.pdf_label.setVisible(is_springer)

        # Update labels associated with DOI, Year, and PDF
        form = self.doi.parentWidget().layout()

        if form is not None:
            for row in range(form.rowCount()):
                label_item = form.itemAt(
                    row,
                    QFormLayout.LabelRole
                )

                field_item = form.itemAt(
                    row,
                    QFormLayout.FieldRole
                )

                if field_item is not None:
                    widget = field_item.widget()

                    if widget == self.doi:
                        label_item.widget().setVisible(is_nature)

                    elif widget == self.year:
                        label_item.widget().setVisible(is_nature)
    
    def write_run_manifest(self):
        import json

        if not getattr(self, "run_manifest_path", None):
            return

        try:
            with open(self.run_manifest_path, "w") as manifest_file:
                json.dump(
                    self.run_manifest,
                    manifest_file,
                    indent=2,
                    allow_nan=False
                )
                manifest_file.write("\n")
        except Exception as e:
            self.log.appendPlainText(
                "WARNING: Could not update run manifest: {}".format(e)
            )

    def refresh_run_manifest_files(self):
        import os

        output_dir = getattr(self, "current_output_dir", None)
        if not output_dir or not os.path.isdir(output_dir):
            return

        files = []
        for root, directories, filenames in os.walk(output_dir):
            directories[:] = [
                directory for directory in directories
                if directory != "__pycache__"
            ]
            for filename in filenames:
                full_path = os.path.join(root, filename)
                relative_path = os.path.relpath(full_path, output_dir)
                if relative_path == "run_manifest.json":
                    continue
                try:
                    size_bytes = os.path.getsize(full_path)
                except OSError:
                    size_bytes = None

                files.append({
                    "path": relative_path,
                    "size_bytes": size_bytes,
                })

        self.run_manifest["output_files"] = sorted(
            files, key=lambda item: item["path"]
        )

    def start_analysis(self):
        if not self.validate_inputs():
            return

        from datetime import datetime
        import os

        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                ".."
            )
        )

        base_run_id = datetime.now().strftime(
            "run_%Y%m%d_%H%M%S"
        )

        runs_root = os.path.join(project_root, "gui_runs")
        os.makedirs(runs_root, exist_ok=True)

        run_id = base_run_id
        suffix = 1

        while True:
            output_dir = os.path.join(runs_root, run_id)
            try:
                os.makedirs(output_dir)
                break
            except FileExistsError:
                run_id = "{}_{:02d}".format(base_run_id, suffix)
                suffix += 1

        self.current_output_dir = output_dir

        publisher = self.publisher.currentText().lower()
        html_source = self.html_source.text().strip()

        doi = self.doi.text().strip()
        year = self.year.text().strip()
        pdf_path = self.pdf_path.text().strip()

        manual_image = None

        if self.input_mode.currentText() == "Manual Image":
            manual_image = self.manual_image_path.text().strip()

        if publisher != "nature":
            doi = None
            year = None

        if publisher != "springer":
            pdf_path = None

        gpu = self.use_gpu.isChecked()

        self.run_manifest_path = os.path.join(
            output_dir,
            "run_manifest.json"
        )
        self.run_manifest = {
            "manifest_version": 1,
            "run_id": run_id,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "input_mode": self.input_mode.currentText(),
            "settings": {
                "publisher": publisher,
                "html_source": html_source or None,
                "doi": doi or None,
                "year": year or None,
                "pdf_path": os.path.abspath(pdf_path) if pdf_path else None,
                "manual_image": (
                    os.path.abspath(manual_image)
                    if manual_image else None
                ),
                "gpu_enabled": bool(gpu),
            },
            "output_directory": os.path.abspath(output_dir),
            "output_files": [],
            "error": None,
        }

        self.write_run_manifest()

        self.status.setText(
            f"Status: Starting {run_id}..."
        )
        self.progress_indicator.show()

        self.start_button.setEnabled(False)

        self.log.clear()
        self.log.appendPlainText(
            "Starting new analysis..."
        )

        self.worker = AnalysisWorker(
            output_dir,
            gpu,
            publisher,
            html_source,
            doi,
            year,
            pdf_path,
            manual_image
        )

        self.worker.progress.connect(
            self.update_status
        )

        self.worker.finished.connect(
            self.analysis_finished
        )

        self.worker.error.connect(
            self.analysis_error
        )

        self.worker.start()
    
    def update_status(self, message):
        self.status.setText(message)
        self.log.appendPlainText(message)
    
    def load_analysis_results(self):
        import json
        import math
        import os
        import statistics

        self.results.clear()

        # Reset previous-run results before loading a new output folder.
        self.images_summary.setText("Images\n0")
        self.objects_summary.setText("Objects\n0")
        self.rods_summary.setText("Rods\n0")
        self.spheres_summary.setText("Spheres\n0")
        self.cubes_summary.setText("Cubes\n0")
        self.triangles_summary.setText("Triangles\n0")
        self.scaled_summary.setText("Images with scale\n0")
        self.object_table.setRowCount(0)
        self.measurement_table.setRowCount(0)
        self.update_measurement_details()
        self.export_results_button.setEnabled(False)
        self.export_detailed_button.setEnabled(False)
        self.export_metadata_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)
        self.analysis_graphs_widget.set_size_data({})

        if not self.current_output_dir:
            self.results.setPlainText(
                "No output directory is available."
            )
            return

        # Clear previous-run images before checking the new results.
        self.annotated_images = []
        self.current_image_index = 0
        self.size_data = {}
        self.show_image()

        sizes_path = os.path.join(
            self.current_output_dir,
            "sizes.json"
        )

        if not os.path.isfile(sizes_path):
            self.results.setPlainText(
                "Analysis completed, but sizes.json was not found."
            )
            return

        try:
            with open(sizes_path, "r") as f:
                self.size_data = json.load(f)

            data = self.size_data
            if not isinstance(data, dict):
                raise ValueError(
                    "sizes.json must contain a JSON object at the top level."
                )

            rod_count = 0
            sphere_count = 0
            cube_count = 0
            triangle_count = 0
            scaled_images = 0
            units = set()

            measurements = {
                "Rod length": [],
                "Rod width": [],
                "Sphere diameter": [],
                "Triangle height": [],
                "Cube side": [],
            }

            for image_name, image_data in data.items():
                if not isinstance(image_data, dict):
                    raise ValueError(
                        "Image entry {!r} must be a JSON object.".format(
                            image_name
                        )
                    )

                size_data = image_data.get("Size", {})
                if not isinstance(size_data, dict):
                    raise ValueError(
                        "Size for image {!r} must be a JSON object.".format(
                            image_name
                        )
                    )

                groups = {}
                for group_name in ("rod", "sphere", "cube", "triangle"):
                    group = size_data.get(group_name, {})
                    if not isinstance(group, dict):
                        raise ValueError(
                            "{!r} measurements for image {!r} must be "
                            "a JSON object.".format(group_name, image_name)
                        )
                    groups[group_name] = group

                rods = groups["rod"]
                spheres = groups["sphere"]
                cubes = groups["cube"]
                triangles = groups["triangle"]

                rod_lengths = rods.get("length", [])
                rod_widths = rods.get("width", [])
                sphere_diameters = spheres.get("diameter", [])
                triangle_heights = triangles.get("height", [])
                cube_sides = cubes.get("side", [])

                for measurement_name, values in (
                    ("rod.length", rod_lengths),
                    ("rod.width", rod_widths),
                    ("sphere.diameter", sphere_diameters),
                    ("triangle.height", triangle_heights),
                    ("cube.side", cube_sides),
                ):
                    if not isinstance(values, list):
                        raise ValueError(
                            "{!r} measurements for image {!r} must be "
                            "a JSON list.".format(
                                measurement_name, image_name
                            )
                        )

                rod_count += len(rod_lengths)
                sphere_count += len(sphere_diameters)
                cube_count += len(cube_sides)
                triangle_count += len(triangle_heights)

                measurement_groups = {
                    "Rod length": rod_lengths,
                    "Rod width": rod_widths,
                    "Sphere diameter": sphere_diameters,
                    "Triangle height": triangle_heights,
                    "Cube side": cube_sides,
                }

                for name, values in measurement_groups.items():
                    for value in values:
                        if (
                            isinstance(value, (int, float))
                            and math.isfinite(value)
                        ):
                            measurements[name].append(value)

                unit = image_data.get("Unit")

                if isinstance(unit, str) and unit.lower() != "nan":
                    scaled_images += 1
                    units.add(unit)

            unit_text = ", ".join(sorted(units)) if units else "None"

            # Update results summary
            self.images_summary.setText(
                "Images\n{}".format(len(data))
            )
            self.objects_summary.setText(
                "Objects\n{}".format(
                    rod_count + sphere_count + cube_count + triangle_count
                )
            )
            self.rods_summary.setText(
                "Rods\n{}".format(rod_count)
            )
            self.spheres_summary.setText(
                "Spheres\n{}".format(sphere_count)
            )
            self.cubes_summary.setText(
                "Cubes\n{}".format(cube_count)
            )
            self.triangles_summary.setText(
                "Triangles\n{}".format(triangle_count)
            )
            self.scaled_summary.setText(
                "Images with scale\n{}".format(scaled_images)
            )

            result_text = (
                "ANALYSIS SUMMARY\n"
                "========================\n"
                "Images analyzed : {}\n"
                "Total objects   : {}\n\n"
                "DETECTED OBJECTS\n"
                "------------------------\n"
                "Rods            : {}\n"
                "Spheres         : {}\n"
                "Cubes           : {}\n"
                "Triangles       : {}\n\n"
                "MEASUREMENTS\n"
                "------------------------\n"
                "Images with scale : {}\n"
                "Units             : {}\n"
            ).format(
                len(data),
                rod_count + sphere_count + cube_count + triangle_count,
                rod_count,
                sphere_count,
                cube_count,
                triangle_count,
                scaled_images,
                unit_text
            )


            self.object_table.setRowCount(0)

            object_counts = [
                ("Rods", rod_count),
                ("Spheres", sphere_count),
                ("Cubes", cube_count),
                ("Triangles", triangle_count),
            ]

            for name, count in object_counts:
                row = self.object_table.rowCount()
                self.object_table.insertRow(row)

                self.object_table.setItem(
                    row, 0, QTableWidgetItem(name)
                )
                self.object_table.setItem(
                    row, 1, QTableWidgetItem(str(count))
                )

            self.measurement_table.setRowCount(0)
            self.update_measurement_details()

            for name, values in measurements.items():
                if values:
                    row = self.measurement_table.rowCount()
                    self.measurement_table.insertRow(row)

                    self.measurement_table.setItem(
                        row, 0, QTableWidgetItem(name)
                    )
                    self.measurement_table.setItem(
                        row, 1, QTableWidgetItem(str(len(values)))
                    )
                    self.measurement_table.setItem(
                        row, 2, QTableWidgetItem("{:.2f}".format(min(values)))
                    )
                    self.measurement_table.setItem(
                        row, 3, QTableWidgetItem("{:.2f}".format(max(values)))
                    )
                    self.measurement_table.setItem(
                        row, 4, QTableWidgetItem(
                            "{:.2f}".format(statistics.mean(values))
                        )
                    )

            # Select the first loaded measurement so its details are visible.
            if self.measurement_table.rowCount() > 0:
                self.measurement_table.setCurrentCell(0, 0)

            # Refresh the details panel after the table has been populated.
            self.update_measurement_details()
            self.results.setPlainText(result_text)

            # Load annotated images
            annotated_dir = os.path.join(
                self.current_output_dir,
                "annotated_subfigures_png"
            )

            self.annotated_images = []

            if os.path.isdir(annotated_dir):
                self.annotated_images = sorted(
                    [
                        os.path.join(annotated_dir, filename)
                        for filename in os.listdir(annotated_dir)
                        if filename.lower().endswith(".png")
                    ]
                )

            self.current_image_index = 0
            self.show_image()

            self.export_results_button.setEnabled(True)
            self.export_detailed_button.setEnabled(
                bool(self.size_data)
            )
            self.export_metadata_button.setEnabled(
                bool(self.size_data)
            )
            self.export_pdf_button.setEnabled(bool(self.size_data))
            self.analysis_graphs_widget.set_size_data(self.size_data)

        except Exception as e:
            # Discard any partially loaded data after a failed load.
            self.size_data = {}
            self.annotated_images = []
            self.current_image_index = 0
            self.show_image()

            self.export_results_button.setEnabled(False)
            self.export_detailed_button.setEnabled(False)
            self.export_metadata_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self.analysis_graphs_widget.set_size_data({})

            self.images_summary.setText("Images\n0")
            self.objects_summary.setText("Objects\n0")
            self.rods_summary.setText("Rods\n0")
            self.spheres_summary.setText("Spheres\n0")
            self.cubes_summary.setText("Cubes\n0")
            self.triangles_summary.setText("Triangles\n0")
            self.scaled_summary.setText("Images with scale\n0")
            self.object_table.setRowCount(0)
            self.measurement_table.setRowCount(0)
            self.update_measurement_details()

            self.results.setPlainText(
                "Could not read analysis results.\n\n"
                "{}: {}".format(
                    type(e).__name__,
                    e
                )
            )

    def get_measurements_for_image(self, image_path):
        """Return size measurements belonging to one annotated image."""

        if not self.size_data:
            return []

        image_name = os.path.basename(image_path)

        # Convert:
        # example.jpg.annotated.png
        # into:
        # example.jpg
        parent_name = image_name.replace(
            ".annotated.png",
            ""
        )

        # Manual-image mode stores measurements under the exact image filename.
        if parent_name in self.size_data:
            return [(parent_name, self.size_data[parent_name])]

        # Paper mode stores measurements under subfigure filenames such as
        # hash.0.jpg, hash.1.jpg, and hash.2.jpg.
        parent_hash = parent_name[:-4]

        matching_data = []

        for filename, measurements in self.size_data.items():
            if not filename.startswith(parent_hash + "."):
                continue

            matching_data.append((filename, measurements))

        return matching_data

    def update_image_details(self, image_path):
        """Display measurements associated with the selected image."""

        if not self.size_data:
            self.image_details.setPlainText(
                "No measurement data available."
            )
            return

        matching_data = self.get_measurements_for_image(
            image_path
        )

        if not matching_data:
            self.image_details.setPlainText(
                "No measurements available for this image."
            )
            return

        lines = []
        lines.append("SUBFIGURES")
        lines.append("-" * 30)

        for filename, measurements in matching_data:
            lines.append(
                os.path.basename(filename)
            )

        lines.append("")
        lines.append("RAW MEASUREMENT DATA")
        lines.append("-" * 30)

        for filename, measurements in matching_data:
            lines.append(
                "{}: {}".format(
                    os.path.basename(filename),
                    measurements
                )
            )

        self.image_details.setPlainText(
            "\n".join(lines)
        )

    def show_image(self):
        if not self.annotated_images:
            self.image_preview.clear()
            self.image_preview.setText(
                "No annotated images available."
            )
            self.image_counter.setText("Image 0 of 0")
            self.previous_image_button.setEnabled(False)
            self.next_image_button.setEnabled(False)
            self.view_large_image_button.setEnabled(False)
            return

        image_path = self.annotated_images[
            self.current_image_index
        ]

        self.image_filename.setText(
            os.path.basename(image_path)
        )

        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            self.image_preview.clear()
            self.image_preview.setText(
                "Could not load selected image."
            )
            self.view_large_image_button.setEnabled(False)
            return

        self.view_large_image_button.setEnabled(True)

        self.image_preview.setPixmap(
            pixmap.scaled(
                self.image_preview.width(),
                self.image_preview.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

        self.image_counter.setText(
            "Image {} of {}".format(
                self.current_image_index + 1,
                len(self.annotated_images)
            )
        )

        self.previous_image_button.setEnabled(
            self.current_image_index > 0
        )

        self.next_image_button.setEnabled(
            self.current_image_index <
            len(self.annotated_images) - 1
        )

        self.update_image_details(image_path)

    def open_large_image(self):
        if not self.annotated_images:
            return

        image_path = self.annotated_images[self.current_image_index]
        viewer = LargeImageViewer(image_path, self)
        viewer.exec_()

    def show_previous_image(self):
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.show_image()

    def show_next_image(self):
        if self.current_image_index < len(self.annotated_images) - 1:
            self.current_image_index += 1
            self.show_image()

    def analysis_finished(self):
        from datetime import datetime

        self.load_analysis_results()

        if getattr(self, "run_manifest", None):
            self.run_manifest["status"] = "completed"
            self.run_manifest["finished_at"] = datetime.now().isoformat()
            self.refresh_run_manifest_files()
            self.write_run_manifest()

        import json
        import os

        sizes_path = os.path.join(
            self.current_output_dir or "",
            "sizes.json"
        )

        has_results = False
        if os.path.isfile(sizes_path):
            try:
                with open(sizes_path, "r") as f:
                    saved_data = json.load(f)
                has_results = isinstance(saved_data, dict) and bool(saved_data)
            except (ValueError, OSError):
                has_results = False

        if has_results:
            self.status.setText(
                "Status: Analysis finished; measurement results loaded."
            )
        else:
            self.status.setText(
                "Status: Pipeline finished, but no measurement results were generated."
            )
            self.log.appendPlainText(
                "WARNING: No valid measurement results were found. "
                "Check the selected input image and analysis logs."
            )

        self.progress_indicator.hide()
        self.start_button.setEnabled(True)

        self.worker = None
    
    def analysis_error(self, message):
        from datetime import datetime

        if getattr(self, "run_manifest", None):
            self.run_manifest["status"] = "failed"
            self.run_manifest["finished_at"] = datetime.now().isoformat()
            self.run_manifest["error"] = str(message)
            self.refresh_run_manifest_files()
            self.write_run_manifest()

        self.status.setText("Error")

        self.log.appendPlainText(
            "ERROR: " + message
        )

        self.progress_indicator.hide()
        self.start_button.setEnabled(True)

        self.worker = None
        



def main():
    app = QApplication(sys.argv)

    stylesheet_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dark_scientific.qss"
    )
    try:
        with open(stylesheet_path, "r") as stylesheet_file:
            app.setStyleSheet(stylesheet_file.read())
    except IOError as exc:
        print("WARNING: Could not load GUI stylesheet: {}".format(exc))

    window = TEMExtractionWindow()
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()