"""Interactive 3D visualization of Mask R-CNN TEM segmentation masks.

The depth is an illustrative extrusion, not a measurement of true particle depth.
Compatible with the project's legacy Python and PyQt5 environment.
"""
import os

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter
from skimage.measure import marching_cubes
from matplotlib import colors as mpl_colors
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QFileDialog, QMessageBox
)


CLASS_NAMES = {
    1: "Particle",
    2: "Rod",
    3: "Cube",
    4: "Triangle",
}

CLASS_COLORS = {
    1: "#45D6C5",
    2: "#58A6FF",
    3: "#B68CFF",
    4: "#FFB86B",
}


class Particle3DViewer(QWidget):
    """Load saved instance masks and display them as extruded 3D objects."""

    def __init__(self, parent=None):
        super(Particle3DViewer, self).__init__(parent)
        self.mask_path = None
        self.data = None
        self.depth_factor = 0.25
        self.mesh_collections = []

        # Coalesce rapid slider events into one geometry rebuild.
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(140)
        self.render_timer.timeout.connect(self._apply_depth_change)

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.load_button = QPushButton("Load Segmentation")
        self.load_button.clicked.connect(self.choose_file)
        toolbar.addWidget(self.load_button)

        toolbar.addWidget(QLabel("Source image:"))
        self.image_combo = QComboBox()
        self.image_combo.setMinimumWidth(150)
        self.image_combo.setToolTip(
            "Choose a segmented image from the current analysis run."
        )
        self.image_combo.currentIndexChanged.connect(
            self._select_source_image
        )
        toolbar.addWidget(self.image_combo)


        toolbar.addWidget(QLabel("Extrusion depth:"))
        self.depth_slider = QSlider(Qt.Horizontal)
        self.depth_slider.setRange(5, 100)
        self.depth_slider.setValue(25)
        self.depth_slider.setToolTip(
            "Illustrative depth only; not a measured particle dimension."
        )
        self.depth_slider.valueChanged.connect(self.depth_changed)
        toolbar.addWidget(self.depth_slider)

        self.depth_label = QLabel("0.25 × mask width")
        toolbar.addWidget(self.depth_label)

        toolbar.addWidget(QLabel("Rendering:"))
        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItem("Realistic surface", "realistic")
        self.render_mode_combo.addItem("Scientific mesh", "mesh")
        self.render_mode_combo.setToolTip(
            "Switch between shaded estimated geometry and its visible mesh."
        )
        self.render_mode_combo.currentIndexChanged.connect(self._update_render_mode)
        toolbar.addWidget(self.render_mode_combo)
        root.addLayout(toolbar)

        self.figure = Figure(figsize=(10, 6), dpi=80, facecolor="#101923")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect("scroll_event", self._on_scroll_zoom)
        self.axes = self.figure.add_subplot(111, projection="3d")
        root.addWidget(self.canvas, 1)

        self.scientific_note = QLabel(
            "One representative particle is shown for each detected class. "
            "Other particles of the same class may have similar shapes, "
            "but their size, orientation, and morphology can differ. "
            "The 3D shapes use detected 2D masks with estimated depth and "
            "rounded surfaces. Hidden geometry is unknown; these are "
            "illustrations, not true reconstructed volumes."
        )
        self.scientific_note.setWordWrap(True)
        self.scientific_note.setStyleSheet(
            "QLabel { color: #8FA6B8; padding: 6px 8px; "
            "background-color: #182431; border: 1px solid #304252; "
            "border-radius: 5px; }"
        )
        root.addWidget(self.scientific_note)

        footer = QHBoxLayout()
        self.status_label = QLabel(
            "Load a .npz segmentation file to explore its particles."
        )
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.reset_button = QPushButton("Reset View")
        self.reset_button.clicked.connect(self.reset_view)
        footer.addWidget(self.reset_button)
        root.addLayout(footer)

        self._show_empty_scene()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open saved segmentation",
            "",
            "Segmentation data (*.npz)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        """Load a saved mask archive without permitting pickle payloads."""
        try:
            with np.load(path, allow_pickle=False) as archive:
                required = ("masks", "class_ids")
                if any(key not in archive.files for key in required):
                    raise ValueError("File must contain masks and class_ids.")

                masks = np.asarray(archive["masks"])
                class_ids = np.asarray(archive["class_ids"], dtype=np.int32)
                scores = (
                    np.asarray(archive["scores"], dtype=np.float32)
                    if "scores" in archive.files
                    else np.ones(len(class_ids), dtype=np.float32)
                )
                image_name = (
                    str(archive["image_name"].item())
                    if "image_name" in archive.files
                    else os.path.basename(path)
                )

            if masks.ndim != 3:
                raise ValueError("Expected masks with shape (height, width, count).")
            if masks.shape[2] != len(class_ids):
                raise ValueError("Mask count does not match class ID count.")
            if len(scores) != len(class_ids):
                raise ValueError("Score count does not match class ID count.")

            self.data = {
                "masks": masks.astype(bool),
                "class_ids": class_ids,
                "scores": scores,
                "image_name": image_name,
            }
            self.mask_path = path

            self.render_scene()
        except Exception as exc:
            QMessageBox.warning(
                self, "Cannot load segmentation",
                "Could not read this mask file:\n{}".format(exc)
            )

    def set_source_files(self, paths):
        """Populate the source-image selector for the active run."""
        paths = list(paths or [])
        previous_path = self.mask_path

        self.image_combo.blockSignals(True)
        self.image_combo.clear()
        for path in paths:
            self.image_combo.addItem(os.path.basename(path), path)
        selected_index = next(
            (i for i, path in enumerate(paths)
             if path == previous_path),
            0 if paths else -1
        )
        self.image_combo.setCurrentIndex(selected_index)
        self.image_combo.blockSignals(False)

        if selected_index >= 0:
            self.load_file(paths[selected_index])
        else:
            self.data = None
            self.mask_path = None
            self.status_label.setText(
                "No saved 3D segmentation files were found for this run."
            )
            self._show_empty_scene()

    def _select_source_image(self, index):
        path = self.image_combo.itemData(index)
        if path and path != self.mask_path:
            self.load_file(path)

    def depth_changed(self, value):
        self.depth_factor = float(value) / 100.0
        self.depth_label.setText("{:.2f} × mask width".format(self.depth_factor))
        self.render_timer.start()

    def _apply_depth_change(self):
        """Scale cached mesh vertices instead of rebuilding the surface."""
        if not self.mesh_collections:
            return

        for collection in self.mesh_collections:
            base_triangles = getattr(
                collection, "_tem_base_triangles", None
            )
            base_depth = float(getattr(collection, "_tem_base_depth", 0.0))
            axes = getattr(collection, "_tem_axes", None)
            particle_width = int(
                getattr(collection, "_tem_particle_width", 1)
            )
            particle_height = int(
                getattr(collection, "_tem_particle_height", 1)
            )
            if base_triangles is None or base_depth <= 0 or axes is None:
                continue

            depth = max(1.0, float(particle_width) * self.depth_factor)
            scaled_triangles = base_triangles.copy()
            scaled_triangles[:, :, 2] *= depth / base_depth
            collection.set_verts(scaled_triangles, closed=True)

            axes.set_zlim(-depth * 0.8, depth * 0.8)
            axes.set_box_aspect((
                max(1, particle_width),
                max(1, particle_height),
                max(1, particle_width) * self.depth_factor
            ))

        self.canvas.draw_idle()

    def _update_render_mode(self, *_args, draw=True):
        """Change mesh visibility styling without rebuilding geometry."""
        mesh_mode = self.render_mode_combo.currentData() == "mesh"
        for collection in self.mesh_collections:
            if mesh_mode:
                collection.set_edgecolor((0.72, 0.86, 0.98, 0.42))
                collection.set_linewidth(0.28)
            else:
                collection.set_edgecolor("none")
                collection.set_linewidth(0.0)
        if draw:
            self.canvas.draw_idle()

    def _on_scroll_zoom(self, event):
        """Zoom the 3D panel under the mouse wheel without rebuilding meshes."""
        axes = getattr(event, "inaxes", None)
        if axes is None or getattr(axes, "name", "") != "3d":
            return

        if event.button == "up":
            factor = 0.80
        elif event.button == "down":
            factor = 1.25
        else:
            return

        for getter, setter in (
            (axes.get_xlim3d, axes.set_xlim3d),
            (axes.get_ylim3d, axes.set_ylim3d),
            (axes.get_zlim3d, axes.set_zlim3d),
        ):
            low, high = getter()
            center = (low + high) * 0.5
            half_range = (high - low) * 0.5 * factor
            if half_range > 0:
                setter(center - half_range, center + half_range)

        self.canvas.draw_idle()

    def reset_view(self):
        self.render_scene()
        for axis in self.figure.axes:
            if getattr(axis, "name", "") == "3d":
                axis.view_init(elev=25, azim=-55)
        self.canvas.draw_idle()

    def _show_empty_scene(self):
        self.figure.clear()
        self.axes = self.figure.add_subplot(111, projection="3d")
        self._style_axes()
        self.axes.set_axis_off()
        self.axes.text2D(
            0.5, 0.53, "3D PARTICLE GALLERY",
            transform=self.axes.transAxes,
            ha="center", va="center", color="#E4EDF5",
            fontsize=16, fontweight="bold"
        )
        self.axes.text2D(
            0.5, 0.45, "Load a saved segmentation to begin",
            transform=self.axes.transAxes,
            ha="center", va="center", color="#8FA6B8",
            fontsize=10
        )
        self.canvas.draw_idle()

    def _style_axes(self):
        self.axes.set_facecolor("#101923")
        self.axes.tick_params(colors="#8FA6B8", labelsize=8)
        self.axes.xaxis.label.set_color("#C9D7E4")
        self.axes.yaxis.label.set_color("#C9D7E4")
        self.axes.zaxis.label.set_color("#C9D7E4")
        for axis in (self.axes.xaxis, self.axes.yaxis, self.axes.zaxis):
            try:
                axis.pane.set_facecolor((0.07, 0.11, 0.15, 1.0))
                axis.pane.set_edgecolor("#304252")
            except AttributeError:
                pass
        self.axes.grid(True, color="#304252", alpha=0.35)
        self.axes.set_xlabel("Image X (px)")
        self.axes.set_ylabel("Image Y (px)")
        self.axes.set_zlabel("Illustrative depth")

    def _add_particle_mesh(self, mask, color, depth, origin_x, origin_y):
        """Create a smooth-shaded, mask-derived surface with estimated depth."""
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return False

        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        crop = np.asarray(
            mask[y_min:y_max + 1, x_min:x_max + 1], dtype=bool
        )
        if crop.size == 0 or not np.any(crop):
            return False

        # Padding gives the signed-distance field a real background around
        # the detected silhouette instead of an artificial crop boundary.
        padded = np.pad(crop, 2, mode="constant", constant_values=False)
        inside_distance = distance_transform_edt(padded)
        outside_distance = distance_transform_edt(~padded)
        signed_distance = inside_distance - outside_distance
        # Smooth the display surface only; never modify the source mask.
        signed_distance = gaussian_filter(
            signed_distance, sigma=0.65
        ).astype(np.float32)
        max_distance = float(inside_distance.max())
        if max_distance <= 0:
            return False

        # Keep the detected cross-section uniform through the depth.
        # Empty outer slices close the mesh with flat end caps; the transition
        # at the silhouette edge provides a small display-only bevel.
        depth_slices = 7
        empty_slice = np.full(
            (1,) + signed_distance.shape, -1.0, dtype=np.float32
        )
        body = np.repeat(
            signed_distance[np.newaxis, :, :],
            depth_slices,
            axis=0
        )
        volume = np.concatenate(
            (empty_slice, body, empty_slice), axis=0
        ).astype(np.float32)

        try:
            vertices, faces, _normals, _values = marching_cubes(
                volume, level=0.0
            )
        except (RuntimeError, ValueError):
            return False

        # Marching-cubes coordinates are (depth, image-y, image-x).
        verts = np.empty((vertices.shape[0], 3), dtype=np.float32)
        verts[:, 0] = (
            vertices[:, 2] + float(origin_x + x_min - 2)
        )
        verts[:, 1] = (
            vertices[:, 1] + float(origin_y + y_min - 2)
        )
        slice_midpoint = (volume.shape[0] - 1) / 2.0
        verts[:, 2] = (
            vertices[:, 0] - slice_midpoint
        ) * float(depth) / float(volume.shape[0] - 1)
        triangles = verts[faces]

        # Average neighboring face normals at each vertex for softer lighting.
        edge_a = triangles[:, 1, :] - triangles[:, 0, :]
        edge_b = triangles[:, 2, :] - triangles[:, 0, :]
        face_normals = np.cross(edge_a, edge_b)
        face_lengths = np.linalg.norm(face_normals, axis=1)
        face_lengths[face_lengths == 0] = 1.0
        face_normals /= face_lengths[:, None]

        vertex_normals = np.zeros_like(verts)
        for corner in range(3):
            np.add.at(vertex_normals, faces[:, corner], face_normals)
        normal_lengths = np.linalg.norm(vertex_normals, axis=1)
        normal_lengths[normal_lengths == 0] = 1.0
        vertex_normals /= normal_lengths[:, None]

        light = np.asarray([-0.35, -0.45, 0.82], dtype=np.float32)
        light /= np.linalg.norm(light)
        vertex_light = 0.38 + 0.62 * np.clip(
            np.dot(vertex_normals, light), 0.0, 1.0
        )
        face_light = vertex_light[faces].mean(axis=1)
        base_rgb = np.asarray(mpl_colors.to_rgb(color), dtype=np.float32)
        face_colors = np.clip(
            face_light[:, None] * base_rgb[None, :], 0.0, 1.0
        )

        collection = Poly3DCollection(
            triangles,
            facecolors=face_colors,
            edgecolors="none",
            linewidths=0.0,
            antialiaseds=True,
            alpha=1.0
        )
        # Cache immutable base geometry for fast depth-slider updates.
        collection._tem_base_triangles = np.array(
            triangles, dtype=np.float32, copy=True
        )
        collection._tem_base_depth = float(depth)
        collection._tem_axes = self.axes
        collection._tem_particle_width = int(crop.shape[1])
        collection._tem_particle_height = int(crop.shape[0])
        self.axes.add_collection3d(collection)
        self.mesh_collections.append(collection)
        return True

    def render_scene(self, *_args):
        """Render one highest-confidence representative per detected class."""
        if self.render_timer.isActive():
            self.render_timer.stop()
        if self.data is None:
            self._show_empty_scene()
            return

        masks = self.data["masks"]
        class_ids = self.data["class_ids"]
        scores = self.data["scores"]
        height, image_width = masks.shape[:2]

        # Keep only classes actually detected, selecting the highest score
        # within each class. At most four panels are expected for this model.
        representatives = []
        for class_id in sorted(set(int(value) for value in class_ids)):
            candidates = [
                index for index, value in enumerate(class_ids)
                if int(value) == class_id
            ]
            if not candidates:
                continue
            best_index = max(candidates, key=lambda index: float(scores[index]))
            mask = masks[:, :, best_index]
            if np.any(mask):
                representatives.append(
                    (class_id, best_index, mask, float(scores[best_index]))
                )

        self.figure.clear()
        self.axes = None
        self.mesh_collections = []

        if not representatives:
            self.axes = self.figure.add_subplot(111, projection="3d")
            self._style_axes()
            self.axes.set_axis_off()
            self.axes.text2D(
                0.5, 0.5, "No non-empty particle masks in this image",
                transform=self.axes.transAxes,
                ha="center", va="center", color="#8FA6B8", fontsize=11
            )
            self.status_label.setText(
                "No renderable detections · {} instance(s) in archive"
                .format(len(class_ids))
            )
            self.canvas.draw_idle()
            return

        panel_count = len(representatives)
        columns = min(2, panel_count)
        rows = int(np.ceil(float(panel_count) / columns))
        self.figure.set_size_inches(
            max(8.0, 5.0 * columns), max(4.8, 4.2 * rows), forward=True
        )

        visible = 0
        for panel_index, item in enumerate(representatives):
            class_id, instance_index, mask, confidence = item
            self.axes = self.figure.add_subplot(
                rows, columns, panel_index + 1, projection="3d"
            )
            self._style_axes()

            ys, xs = np.nonzero(mask)
            x_min, x_max = int(xs.min()), int(xs.max())
            y_min, y_max = int(ys.min()), int(ys.max())
            particle_width = max(1, x_max - x_min + 1)
            particle_height = max(1, y_max - y_min + 1)
            depth = max(1.0, float(particle_width) * self.depth_factor)
            color = CLASS_COLORS.get(class_id, "#D5DEE7")

            if not self._add_particle_mesh(mask, color, depth, 0, 0):
                continue
            self._update_render_mode(draw=False)

            margin_x = max(3, int(particle_width * 0.15))
            margin_y = max(3, int(particle_height * 0.15))
            self.axes.set_xlim(max(0, x_min - margin_x),
                               min(image_width, x_max + margin_x + 1))
            self.axes.set_ylim(min(height, y_max + margin_y + 1),
                               max(0, y_min - margin_y))
            self.axes.set_zlim(-depth * 0.8, depth * 0.8)
            self.axes.view_init(elev=25, azim=-55)
            self.axes.set_box_aspect((
                max(1, particle_width),
                max(1, particle_height),
                max(1, particle_width) * self.depth_factor
            ))
            class_name = CLASS_NAMES.get(
                class_id, "Class {}".format(class_id)
            )
            self.axes.set_title(
                "{} · {:.1f}% confidence".format(
                    class_name, confidence * 100.0
                ),
                color="#E4EDF5", pad=10, fontsize=10
            )
            self.axes.tick_params(labelsize=6)
            visible += 1

        self.figure.suptitle(
            os.path.basename(self.data["image_name"]),
            color="#E4EDF5", fontsize=10, y=0.99
        )
        self.figure.tight_layout(rect=(0, 0, 1, 0.96))
        self.status_label.setText(
            "{} class representative(s) shown · {} instance(s) detected · "
            "highest-confidence instance selected per class"
            .format(visible, len(class_ids))
        )
        self.canvas.draw_idle()
