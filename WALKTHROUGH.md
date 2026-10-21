# Walkthrough: How this UI works

This guide is for someone with intermediate Python experience who wants to understand the design and change the code.

## 1. Why three layers?

```text
sample_mission.csv  ->  data_model.MissionData  ->  app.Dashboard  ->  graphs/table
                                  ^                       |
                                  |                       v
                           schema validation       buttons/slider events
```

The CSV is the official recording format. `data_model.py` contains the data rules and calculations so the UI (`app.py`) doesn't have to know how to validate the file. PySide6 builds the interface; PyQtGraph draws the trajectory and time-series graphs.

## 2. Read and validate data

In `MissionData.from_csv(path)`:

- `pd.read_csv()` loads the file into a DataFrame.
- The code checks all eight required columns exist.
- `pd.to_numeric()` verifies numeric columns, and NumPy tests that numbers are finite.
- Phase strings cannot be blank, and timestamps must increase strictly.
- The class stores the validated DataFrame as `mission.frame`.

The UI can assume `mission.frame` is already in an approved format, and errors are shown in a dialog instead of crashing the app.

## 3. Separate the data analysis from drawing

`MissionData.distance_m` uses consecutive position differences to calculate 3D path length:

```python
xyz = frame[["x_m", "y_m", "z_m"]].to_numpy(dtype=float)
step_lengths = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
total_distance = step_lengths.sum()
```

This is distance traveled along the recorded path, not simply the start-to-finish displacement. `z_m` is treated as a Z coordinate (no assumption about whether positive Z is upward/downward).

## 4. Construct the window (Qt)

`Dashboard` inherits from `QMainWindow`, which supplies the window and status bar. `build_interface()` creates layouts and widgets:

- `QPushButton` to open a file.
- `QComboBox` to select a phase.
- `QSlider` to choose a recorded sample.
- `QTabWidget` for replay, raw data, and preflight placeholder.
- `QTableView` displays values through `CsvTableModel`.
- `pg.PlotWidget` draws XY trajectory and the four telemetry plots.

Qt layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`) determine placement, so you aren't manually setting pixel coordinates for every widget.

## 5. Connect user actions using signals and slots

When the user clicks **Open mission CSV**, Qt emits a `clicked` signal:

```python
load_button.clicked.connect(self.choose_file)
```

`choose_file()` uses `QFileDialog.getOpenFileName()` and calls `load_mission(path)`. `load_mission()` validates the file, updates the metric labels, populates the phase selector, and regenerates graphs.

Similarly:

```python
self.phase_combo.currentIndexChanged.connect(self.change_phase)
self.slider.valueChanged.connect(self.move_to_sample)
```

You don't write your own infinite input-checking loop. Qt listens for GUI events and invokes your callbacks.

## 6. Draw data with PyQtGraph

The trajectory is a 2D plot:

```python
self.trajectory.plot(df["x_m"], df["y_m"])
```

The time-series graphs use `elapsed_sim_s` on the horizontal axis and one column per vertical axis. All points are from the current filtered view (`self.view`), not fabricated. `setAspectLocked(True)` on the XY chart makes distance scales physically consistent. Since the sample almost never moves in Z, a tiny Z range is shown on a broader axis to prevent magnifying microscopic numerical changes.

## 7. Filter and replay

`MissionData.subset(phase)` filters DataFrame rows. If `None`, it returns all rows. After a filter change, the slider range is updated to match the number of visible rows.

On slider movement, `move_to_sample(index)` uses `self.view.iloc[index]` to find the row. It moves a yellow point on the trajectory and a yellow time cursor on each telemetry chart.

The Play button uses `QTimer`, which schedules a callback without blocking the GUI. The delay to the next sample comes from the difference in simulation timestamps. This uses the CSV's times, not a fixed 100-millisecond guess.

## 8. Why preflight cannot be green yet

The mission CSV has commanded thrust and rudder values and motion coordinates. It does **not** have batteries, leak sensor alerts, actual motor feedback, CPU temperatures, or ROS 2 node states. Consequently, the preflight tab is clearly marked *not connected*. You must agree with the team on a separate diagnostics interface before implementing reliable pass/fail checks.

## 9. Where to edit functionality

| Change you want | Edit here |
|---|---|
| Change colors or fonts | `Dashboard.stylesheet()` and the color constants at top of `app.py` |
| Rearrange the panels | `Dashboard.build_interface()` |
| Add another graph for an existing numeric column | `Dashboard.series` in `build_interface()` |
| Change what happens when a CSV is opened | `Dashboard.load_mission()` |
| Calculate a new summary metric | `MissionData` in `data_model.py` |
| Change the official CSV schema | `REQUIRED_COLUMNS` and validation code in `data_model.py` (only with team agreement) |
| Add real pre-mission checks | Create a separate diagnostics loader and populate the preflight tab; don't repurpose motion CSV fields |

## 10. Suggested experiments

1. Change the line color of the XY trajectory.
2. Add another label that displays `heading_deg` for the current slider sample.
3. Filter by **Turn** and verify the raw table still shows the *entire* original recording.
4. Intentionally delete one required column in a **copy** of the CSV, then try to open it. Notice the error handling.
5. Add a derived column `rudder_deg = np.degrees(command_rudder_rad)` in the data processing layer and plot it, without changing the team's official exported CSV schema.

## 11. Testing notes

Run the unit tests via:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

All five included tests cover the CSV loading/validation/calculation layer. The Qt GUI needs a local graphical Python environment for runtime testing; syntax checks alone are not a substitute for launching it on Windows.
