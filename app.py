"""Desktop UI for offline AUV mission telemetry CSVs.

Run on Windows: .\\.venv\\Scripts\\python.exe app.py
"""

import sys
from pathlib import Path

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from data_model import MissionData, SensorData

BG = "#0b1220"
PANEL = "#111d30"
BLUE = "#38bdf8"
GREEN = "#34d399"
YELLOW = "#fbbf24"
TEXT = "#ecf3ff"
MUTED = "#9fb0c7"


class CsvTableModel(QAbstractTableModel):
    """Adapter that lets a Qt table display a pandas DataFrame."""

    def __init__(self):
        super().__init__()
        self.frame = pd.DataFrame()

    def set_frame(self, frame: pd.DataFrame) -> None:
        self.beginResetModel()
        self.frame = frame
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.frame)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.frame.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self.frame.iat[index.row(), index.column()]
        if isinstance(value, float):
            return f"{value:.5f}"
        return str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self.frame.columns[section])
        return str(section + 1)


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mission: MissionData | None = None
        self.sensor: SensorData | None = None
        self.view = pd.DataFrame()
        self.cursors: list[pg.InfiniteLine] = []
        self.marker = pg.ScatterPlotItem(size=13, pen=pg.mkPen("#ffffff", width=1), brush=YELLOW)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)  # Schedule each step using the next CSV timestamp.
        self.timer.timeout.connect(self.advance)

        self.setWindowTitle("AUV Mission Console | Offline Analysis")
        self.resize(1480, 900)
        self.setStyleSheet(self.stylesheet())
        pg.setConfigOptions(antialias=True, foreground=MUTED)

        self.build_interface()
        self.statusBar().showMessage("Ready: load a mission CSV")

        sample = Path(__file__).resolve().parent / "sample_mission.csv"
        if sample.exists():
            self.load_mission(sample)

    def stylesheet(self) -> str:
        return f"""
            QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI'; font-size: 12px; }}
            QFrame#metric {{ background: {PANEL}; border-radius: 10px; }}
            QFrame#panel {{ background: {PANEL}; border-radius: 10px; }}
            QPushButton {{ background: #195783; border: 1px solid #3177a3; border-radius: 7px;
                           padding: 9px 15px; font-weight: 600; }}
            QPushButton:hover {{ background: #236d9e; }}
            QComboBox {{ background: {PANEL}; padding: 7px; border: 1px solid #34506b; border-radius: 6px; }}
            QTabWidget::pane {{ border: 1px solid #26384d; }}
            QTabBar::tab {{ padding: 10px 20px; background: #101a2a; }}
            QTabBar::tab:selected {{ background: #214361; }}
            QSlider::groove:horizontal {{ height: 6px; background: #26384d; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {YELLOW}; width: 15px;
                                          margin: -5px 0; border-radius: 7px; }}
            QTableView {{ background: {PANEL}; gridline-color: #26384d; }}
            QHeaderView::section {{ background: #18314b; padding: 8px; border: 0; }}
            QStatusBar {{ color: {MUTED}; }}
        """

    def label(self, text: str, size=12, color=TEXT, bold=False) -> QLabel:
        widget = QLabel(text)
        widget.setStyleSheet(
            f"font-size: {size}px; color: {color}; font-weight: {700 if bold else 400};"
        )
        return widget

    def create_metric(self, title: str) -> tuple[QFrame, QLabel]:
        panel = QFrame()
        panel.setObjectName("metric")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(17, 13, 17, 13)
        layout.addWidget(self.label(title.upper(), 11, MUTED, True))
        value = self.label("—", 22, TEXT, True)
        layout.addWidget(value)
        return panel, value

    def make_plot(self, title: str, x_label: str, y_label: str) -> pg.PlotWidget:
        plot = pg.PlotWidget(background=PANEL)
        plot.setTitle(title, color=TEXT, size="11pt")
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", y_label)
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.getPlotItem().hideButtons()
        return plot

    def build_interface(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 10)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_area = QVBoxLayout()
        title_area.addWidget(self.label("AUV  /  MISSION CONSOLE", 23, TEXT, True))
        self.file_label = self.label("Offline mission analysis • no live robot connection", 12, MUTED)
        title_area.addWidget(self.file_label)
        header.addLayout(title_area, 1)
        load_button = QPushButton("Open mission CSV")
        load_button.clicked.connect(self.choose_file)
        header.addWidget(load_button)
        outer.addLayout(header)

        metric_row = QHBoxLayout()
        self.metric_values = {}
        for key, title in [
            ("samples", "Samples"),
            ("duration", "Duration"),
            ("distance", "3D path length"),
            ("z", "Z position range"),
            ("phases", "Mission phases"),
        ]:
            panel, value = self.create_metric(title)
            self.metric_values[key] = value
            metric_row.addWidget(panel)
        outer.addLayout(metric_row)

        tabs = QTabWidget()
        outer.addWidget(tabs, 1)

        replay_tab = QWidget()
        replay_layout = QVBoxLayout(replay_tab)
        replay_layout.setSpacing(12)

        controls = QHBoxLayout()
        controls.addWidget(self.label("Show phase:", 12, MUTED))
        self.phase_combo = QComboBox()
        self.phase_combo.addItem("All phases", None)
        self.phase_combo.currentIndexChanged.connect(self.change_phase)
        controls.addWidget(self.phase_combo)
        controls.addStretch()
        self.quality_label = self.label("No file loaded", 11, MUTED)
        controls.addWidget(self.quality_label)
        replay_layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.trajectory = self.make_plot("XY TRAJECTORY", "X (m)", "Y (m)")
        self.trajectory.setAspectLocked(True)  # One meter in X = one meter in Y.
        splitter.addWidget(self.trajectory)

        grid_frame = QWidget()
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.series = [
            ("heading_deg", "HEADING", "deg", BLUE),
            ("command_thrust_N", "COMMANDED THRUST", "N", GREEN),
            ("command_rudder_rad", "COMMANDED RUDDER", "rad", "#c084fc"),
            ("z_m", "Z POSITION", "m", "#fb7185"),
        ]
        self.plots = {}
        for i, (column, title, unit, _) in enumerate(self.series):
            plot = self.make_plot(title, "Elapsed time (s)", unit)
            self.plots[column] = plot
            grid.addWidget(plot, i // 2, i % 2)
        splitter.addWidget(grid_frame)
        splitter.setSizes([520, 850])
        replay_layout.addWidget(splitter, 1)

        timeline = QHBoxLayout()
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        timeline.addWidget(self.play_button)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self.move_to_sample)
        timeline.addWidget(self.slider, 1)
        self.sample_label = self.label("Choose a CSV to inspect mission telemetry", 12, MUTED)
        self.sample_label.setMinimumWidth(425)
        timeline.addWidget(self.sample_label)
        replay_layout.addLayout(timeline)
        tabs.addTab(replay_tab, "Mission replay")

        # A separate offline CSV can store water sensors independently of AUV motion.
        sensor_tab = QWidget()
        sensor_layout = QVBoxLayout(sensor_tab)
        sensor_layout.setSpacing(12)

        sensor_header = QHBoxLayout()
        sensor_header.addWidget(self.label("SENSOR DATA", 17, TEXT, True))
        self.sensor_file_label = self.label("No sensor CSV loaded", 12, MUTED)
        sensor_header.addWidget(self.sensor_file_label, 1)
        sensor_load_button = QPushButton("Open sensor CSV")
        sensor_load_button.clicked.connect(self.choose_sensor_file)
        sensor_header.addWidget(sensor_load_button)
        sensor_layout.addLayout(sensor_header)

        sensor_controls = QHBoxLayout()
        sensor_controls.addWidget(self.label("View:", 12, MUTED))
        self.sensor_mode_combo = QComboBox()
        self.sensor_mode_combo.addItem("Time series", "time")
        self.sensor_mode_combo.addItem("Depth profile", "depth")
        self.sensor_mode_combo.currentIndexChanged.connect(self.draw_sensor_plots)
        sensor_controls.addWidget(self.sensor_mode_combo)
        sensor_controls.addSpacing(15)
        sensor_controls.addWidget(self.label("Depth source:", 12, MUTED))
        self.sensor_depth_combo = QComboBox()
        self.sensor_depth_combo.addItem("Sensor CSV depth_m", "csv")
        self.sensor_depth_combo.addItem("Mission -Z (negative Z is down)", "mission_minus_z")
        self.sensor_depth_combo.addItem("Mission +Z (positive Z is down)", "mission_plus_z")
        self.sensor_depth_combo.currentIndexChanged.connect(self.draw_sensor_plots)
        self.sensor_depth_combo.setEnabled(False)
        sensor_controls.addWidget(self.sensor_depth_combo)
        sensor_controls.addStretch()
        for col, title in (("temperature_c", "Temperature"), ("ph", "pH"), ("voltage_v", "Voltage")):
            # Check boxes let viewers compare selected measurements side by side.
            if not hasattr(self, "sensor_checks"):
                self.sensor_checks = {}
            check = QCheckBox(title)
            check.setChecked(True)
            check.toggled.connect(self.draw_sensor_plots)
            self.sensor_checks[col] = check
            sensor_controls.addWidget(check)
        sensor_layout.addLayout(sensor_controls)

        self.sensor_status = self.label(
            "Load a sensor CSV with time, temperature, pH, and voltage; depth_m is optional.",
            12, MUTED,
        )
        self.sensor_status.setWordWrap(True)
        sensor_layout.addWidget(self.sensor_status)

        sensor_graph_frame = QWidget()
        sensor_graphs_layout = QHBoxLayout(sensor_graph_frame)
        sensor_graphs_layout.setContentsMargins(0, 0, 0, 0)
        sensor_graphs_layout.setSpacing(10)
        self.sensor_series = [
            ("temperature_c", "TEMPERATURE", "°C", "#38bdf8"),
            ("ph", "PH", "pH", "#c084fc"),
            ("voltage_v", "BATTERY VOLTAGE", "V", "#34d399"),
        ]
        self.sensor_plots = {}
        for col, title, unit, _ in self.sensor_series:
            plot = self.make_plot(title, "Time (s)", unit)
            self.sensor_plots[col] = plot
            sensor_graphs_layout.addWidget(plot, 1)
        sensor_layout.addWidget(sensor_graph_frame, 3)

        sensor_layout.addWidget(self.label("RAW SENSOR SAMPLES", 12, MUTED, True))
        self.sensor_table_model = CsvTableModel()
        sensor_table = QTableView()
        sensor_table.setModel(self.sensor_table_model)
        sensor_table.setAlternatingRowColors(True)
        sensor_table.horizontalHeader().setStretchLastSection(True)
        sensor_layout.addWidget(sensor_table, 1)
        tabs.addTab(sensor_tab, "Sensor data")

        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        data_layout.addWidget(self.label("RAW MISSION SAMPLES", 15, TEXT, True))
        data_layout.addWidget(self.label("All original samples, in timestamp order.", 12, MUTED))
        self.table_model = CsvTableModel()
        table = QTableView()
        table.setModel(self.table_model)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        data_layout.addWidget(table)
        tabs.addTab(data_tab, "Raw CSV data")

        preflight_tab = QWidget()
        preflight_layout = QVBoxLayout(preflight_tab)
        preflight_layout.setContentsMargins(35, 30, 35, 30)
        preflight_layout.addWidget(self.label("PREFLIGHT / NOT CONNECTED", 20, YELLOW, True))
        preflight_layout.addWidget(self.label(
            "This CSV records movement and control commands, not hardware diagnostics.", 14, TEXT
        ))
        preflight_layout.addWidget(self.label(
            "Future preflight checks need a separate source for battery status, sensor health, "
            "thruster status, and ROS 2 node availability. Do not interpret CSV validation as "
            "proof that the physical AUV is ready to deploy.", 13, MUTED
        ))
        preflight_layout.addStretch()
        tabs.addTab(preflight_tab, "Preflight (future)")

    def choose_sensor_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open AUV sensor CSV", str(Path.home()), "CSV files (*.csv)"
        )
        if path:
            self.load_sensor(Path(path))

    def load_sensor(self, path: Path):
        try:
            new_sensor = SensorData.from_csv(path)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid sensor CSV", str(exc))
            self.statusBar().showMessage("Sensor load failed; previous data remains open")
            return

        self.sensor = new_sensor
        self.sensor_file_label.setText(f"Loaded: {path.name}  •  {len(new_sensor.frame):,} samples")
        self.sensor_table_model.set_frame(new_sensor.frame)
        self.draw_sensor_plots()
        self.statusBar().showMessage(f"Loaded sensor file: {path.name}")

    def draw_sensor_plots(self, _change=None):
        """Plot each selected sensor against elapsed time or positive-down depth."""
        mode = self.sensor_mode_combo.currentData()
        depth_mode = mode == "depth"
        self.sensor_depth_combo.setEnabled(depth_mode)

        for col, _, _, _ in self.sensor_series:
            self.sensor_plots[col].clear()
            self.sensor_plots[col].setVisible(self.sensor_checks[col].isChecked())

        if self.sensor is None:
            return

        df = self.sensor.frame
        depth = None
        if depth_mode:
            try:
                depth = self.sensor.depth_for_profile(
                    source=self.sensor_depth_combo.currentData(), mission=self.mission
                )
            except ValueError as exc:
                self.sensor_status.setText(str(exc))
                return
            valid = pd.notna(depth)
            count = int(valid.sum())
            self.sensor_status.setText(
                f"Depth increases downward • {count}/{len(df)} valid depth matches. "
                "For mission Z: clocks must match; Z=0 must be the water surface."
            )
        else:
            self.sensor_status.setText(
                f"Time series • {len(df):,} sensor samples. Time is assumed to be elapsed seconds."
            )

        for col, _, unit, color in self.sensor_series:
            plot = self.sensor_plots[col]
            plot.getViewBox().invertY(depth_mode)
            vals = df[col].to_numpy(dtype=float)
            if depth_mode:
                plot.setLabel("bottom", unit)
                plot.setLabel("left", "Depth (m)")
                # Point clouds (value vs. depth) resemble oceanographic profiles.
                plot.plot(
                    vals[valid], depth[valid], pen=None, symbol="o", symbolSize=6,
                    symbolPen=None, symbolBrush=pg.mkBrush(color),
                )
            else:
                plot.setLabel("bottom", "Time (s)")
                plot.setLabel("left", unit)
                plot.plot(
                    df["time_s"].to_numpy(dtype=float), vals,
                    pen=pg.mkPen(color, width=2), symbol="o", symbolSize=4,
                    symbolPen=None, symbolBrush=pg.mkBrush(color),
                )
            plot.enableAutoRange()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open AUV mission CSV", str(Path.home()), "CSV files (*.csv)"
        )
        if path:
            self.load_mission(Path(path))

    def load_mission(self, path: Path):
        try:
            new_mission = MissionData.from_csv(path)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid mission CSV", str(exc))
            self.statusBar().showMessage("Load failed; previous mission remains open")
            return

        self.timer.stop()
        self.play_button.setText("▶ Play")
        self.mission = new_mission
        df = self.mission.frame
        self.file_label.setText(f"Loaded: {path.name}  •  Offline data only")
        self.metric_values["samples"].setText(f"{len(df):,}")
        self.metric_values["duration"].setText(f"{self.mission.duration_s:.2f} s")
        self.metric_values["distance"].setText(f"{self.mission.distance_m:.2f} m")
        low, high = self.mission.z_range_m
        self.metric_values["z"].setText(f"{low:.3f}–{high:.3f} m")
        self.metric_values["phases"].setText(str(len(self.mission.phases)))
        self.quality_label.setText("CSV schema valid  •  finite values  •  increasing time")
        self.table_model.set_frame(df)

        self.phase_combo.blockSignals(True)
        self.phase_combo.clear()
        self.phase_combo.addItem("All phases", None)
        for phase in self.mission.phases:
            self.phase_combo.addItem(phase, phase)
        self.phase_combo.blockSignals(False)
        self.change_phase()
        if self.sensor is not None and self.sensor_mode_combo.currentData() == "depth":
            self.draw_sensor_plots()
        self.statusBar().showMessage(f"Loaded {path.name}: {len(df)} samples")

    def change_phase(self, _index=None):
        if self.mission is None:
            return
        self.timer.stop()
        self.play_button.setText("▶ Play")
        self.view = self.mission.subset(self.phase_combo.currentData())
        self.draw_plots()
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.view) - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.move_to_sample(0)

    def draw_plots(self):
        df = self.view
        x = df["x_m"].to_numpy()
        y = df["y_m"].to_numpy()
        t = df["elapsed_sim_s"].to_numpy()

        self.trajectory.clear()
        self.trajectory.plot(x, y, pen=pg.mkPen(BLUE, width=2.5))
        self.trajectory.plot([x[0]], [y[0]], pen=None, symbol="o", symbolSize=10, symbolBrush=GREEN)
        self.trajectory.plot([x[-1]], [y[-1]], pen=None, symbol="o", symbolSize=10, symbolBrush="#fb7185")
        self.marker = pg.ScatterPlotItem(size=13, pen=pg.mkPen("#ffffff", width=1), brush=YELLOW)
        self.trajectory.addItem(self.marker)
        self.trajectory.enableAutoRange()

        self.cursors = []
        for col, _, _, color in self.series:
            plot = self.plots[col]
            plot.clear()
            plot.plot(t, df[col].to_numpy(), pen=pg.mkPen(color, width=2))
            cursor = pg.InfiniteLine(pos=float(t[0]), angle=90, pen=pg.mkPen(YELLOW, width=1))
            plot.addItem(cursor)
            self.cursors.append(cursor)
            plot.enableAutoRange()
            if col == "z_m":
                # Prevent tiny floating-point fluctuations around a constant Z
                # from looking like major vertical movement on a zoomed axis.
                lower, upper = float(df[col].min()), float(df[col].max())
                if upper - lower < 0.1:
                    plot.setYRange(lower - 0.5, upper + 0.5, padding=0)

    def move_to_sample(self, index: int):
        if self.view.empty:
            return
        row = self.view.iloc[index]
        self.marker.setData([float(row["x_m"])], [float(row["y_m"])])
        for cursor in self.cursors:
            cursor.setPos(float(row["elapsed_sim_s"]))
        self.sample_label.setText(
            f"t={row['elapsed_sim_s']:.2f}s  |  {row['phase']}  |  "
            f"X={row['x_m']:.2f}, Y={row['y_m']:.2f} m"
        )

    def toggle_play(self):
        if self.view.empty:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("▶ Play")
        else:
            if self.slider.value() == self.slider.maximum():
                self.slider.setValue(0)
            self.play_button.setText("Ⅱ Pause")
            self.schedule_next()

    def schedule_next(self):
        """Match replay speed to the simulation time gaps in the CSV."""
        current = self.slider.value()
        if current >= self.slider.maximum():
            self.play_button.setText("▶ Play")
            return
        t0 = float(self.view.iloc[current]["elapsed_sim_s"])
        t1 = float(self.view.iloc[current + 1]["elapsed_sim_s"])
        delay_ms = max(1, round((t1 - t0) * 1000))
        self.timer.start(delay_ms)

    def advance(self):
        if self.slider.value() >= self.slider.maximum():
            self.play_button.setText("▶ Play")
        else:
            self.slider.setValue(self.slider.value() + 1)
            self.schedule_next()


def main():
    app = QApplication(sys.argv)
    window = Dashboard()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
