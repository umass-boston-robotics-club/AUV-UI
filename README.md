# AUV Mission Dashboard

A Python desktop application for **offline post-mission analysis** AUV telemetry CSV format. Includes a mission replay slider, phase filter, 2D XY trajectory, heading/thrust/rudder/Z graphs, raw data table, schema validation, and a clearly disabled preflight placeholder.

**No ROS 2 installation or connection to the robot is needed for this version.** The UI is intentionally an offline analysis tool. It does not measure hardware health.

## Folder contents

- `app.py` — PySide6 desktop application; visual components and interaction events.
- `data_model.py` — CSV schema checking, Pandas loading, and calculations.
- `sample_mission.csv` — a 199-row simulation CSV.
- `tests/test_data_model.py` — basic unit tests.
- `requirements.txt` — external Python libraries.

## Windows setup (PowerShell, VS Code)

From the folder containing `app.py`:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

These commands **do not require activating** the virtual environment. If you installed a different supported Python version, use that instead of `-3.10`, e.g. `py -3.11`.

Use **File > Open Folder** in VS Code to open this project. The app auto-loads `sample_mission.csv` when started from the project directory. Click **Open mission CSV** to load another CSV with the same schema.

## CSV format

```text
elapsed_sim_s,phase,x_m,y_m,z_m,heading_deg,command_thrust_N,command_rudder_rad
```

All columns except `phase` must have finite numeric values, `phase` must be nonempty, and `elapsed_sim_s` must be strictly increasing. Additional columns in a file are ignored (and won't appear in the raw data table).

- `elapsed_sim_s`: simulation seconds (not wall-clock time)
- `phase`: phase label
- `x_m`, `y_m`, `z_m`: position coordinates in meters; `z_m` is not automatically interpreted as depth
- `heading_deg`: heading angle in degrees
- `command_thrust_N`: **commanded** thrust in newtons (not measured thrust)
- `command_rudder_rad`: **commanded** rudder angle in radians (not measured rudder deflection)

The dashboard's 3D path length is the sum of Euclidean distances between successive XYZ points. Duration is `last elapsed_sim_s - first elapsed_sim_s`. 

## Try it

1. Open the app, which auto-loads the sample mission.
2. Look at the XY trajectory on the left and four telemetry plots on the right.
3. Drag the replay slider. Its yellow marker moves through the trajectory and the vertical cursors move on the plots.
4. Press **Play** to advance through the selected samples. Playback uses the time differences between consecutive CSV rows, so a gap in the timestamps produces a longer delay.
5. Filter by **Turn**. All plots and the slider now show only that phase.
6. Open **Raw CSV data** to inspect the underlying values.
7. Open **Preflight (future)** to see which information this CSV cannot supply.

## Test the data-processing layer

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Future ROS 2 integration

For offline missions, it will be possible to convert ROS 2 bag/topic data into the same CSV schema and the UI code does not need to change. For actual preflight checks, separate diagnostics interface (e.g. dedicated ROS 2 diagnostic topics or an explicit JSON diagnostics report).
