# AUV Mission Dashboard

A Python desktop application developed for the **UMass Boston Robotics Club** to visualize and analyze autonomous underwater vehicle (AUV) telemetry after a mission. The dashboard reads CSV files **offline**; it does **not** require a live ROS 2 connection or communicate directly with physical sensors.

## Features

### Mission telemetry and replay

- Load a mission telemetry CSV and validate required fields, numeric values, mission phases, and increasing timestamps.
- Replay recorded movement with play/pause controls and a timeline slider that follows the recorded timestamp intervals.
- Filter the replay by mission phase.
- Plot the AUV's **XY trajectory**, **heading**, **commanded thrust**, **commanded rudder**, and **Z position**.
- Display mission summary metrics, including sample count, duration, cumulative 3D path length, Z-position range, and number of mission phases.
- Inspect mission records in the **Raw CSV data** tab.

### New: Sensor data visualization

This update adds a dedicated **Sensor data** tab to load and visualize measurements expected from the AUV's sensors. The sensor data is read from a **separate recorded CSV file**, independently of the mission telemetry CSV.

- **Temperature graph:** Plot recorded water temperature in **degrees Celsius (°C)**.
- **pH graph:** Plot recorded **pH** measurements.
- **Battery voltage graph:** Plot recorded voltage in **volts (V)**.
- **Time-series view:** Display temperature, pH, and voltage against elapsed time in seconds.
- **Depth-profile view:** Display these measurements against depth when valid depth data is available. Depth increases downward in this view.
- **Flexible depth sources:** Use `depth_m` recorded in the sensor CSV, or derive depth by interpolating mission `z_m` values at the sensor timestamps. The user selects whether mission Z increases or decreases with depth.
- **Graph selection:** Show or hide individual sensor graphs using checkboxes.
- **Raw sensor samples:** Inspect the loaded readings in a table beneath the sensor graphs.
- **Sensor CSV validation:** Recognize several common column-header spellings, require numeric and finite measurements, reject duplicate/descending timestamps, and reject negative recorded depths.

> **Important:** These graphs display values supplied in CSV files; they do not retrieve live readings from connected sensors. If deriving depth from mission Z, both files must use the same elapsed-seconds clock, mission `Z = 0` must represent the water surface, and the selected Z direction must be correct. Measurements outside the mission time range are not extrapolated.

## Changes in `feature/dashboard-updates`

| File | Changes |
| --- | --- |
| `data_model.py` | Corrected the older copy and added `SensorData` for loading and validating sensor measurements, recognizing alternate CSV headers, and calculating depth profiles. Existing `MissionData` calculations remain available. |
| `app.py` | Expanded the desktop interface with a dedicated sensor tab, temperature/pH/battery-voltage graphs, time-series/depth-profile modes, depth-source controls, and a raw sensor readings table. |
| `README.md` | Documented the new sensor capabilities, expected CSV formats, and planned interface improvements. |

## CSV formats

### Mission CSV

The mission file requires these columns:

```csv
elapsed_sim_s,phase,x_m,y_m,z_m,heading_deg,command_thrust_N,command_rudder_rad
```

All columns except `phase` must contain valid finite numbers; timestamps must increase strictly from row to row.

### Sensor CSV

The sensor file requires **elapsed time, temperature, pH, and voltage**; recorded depth is optional. Canonical names are:

```csv
time_s,temperature_c,ph,voltage_v,depth_m
0,18.2,7.4,12.6,0
1,18.3,7.3,12.5,0.5
2,18.4,7.3,12.5,1.0
```

This is an **illustrative example**, not a file bundled with the project. If you don't have depth measurements yet, omit the `depth_m` column and use the time-series view (or provide compatible mission Z data for depth profiles).

The parser also accepts alternative header spellings such as `time`, `elapsed_sim_s`, `temperature`, `temp_c`, `water_ph`, `battery_voltage`, and `depth`. Time values must represent **elapsed seconds**, and measurement columns must contain finite numeric values. If `depth_m` is supplied, it must be nonnegative (`0` means the water surface).

## Run locally

From the project directory, in **Windows PowerShell**:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The dashboard uses **PySide6**, **pyqtgraph**, **pandas**, and **NumPy**. Ensure these packages are included in `requirements.txt` for the updated interface.

To load sensor readings, open the **Sensor data** tab and click **Open sensor CSV**. The project may also load `sample_mission.csv` automatically, if that file exists in the project directory.

## Planned improvements

- [ ] **Show coordinates when hovering:** On the XY trajectory graph, show the hovered data point's `(x, y)` coordinates, including units.
- [ ] **Improve the raw sensor data table:** Make recorded sensor measurements easier to read and navigate with better column widths, labeling, and layout.
- [ ] **Better dashboard organization:** Reorganize the mission, sensor graph, and raw-data sections so controls and visualizations are more intuitive and less cluttered.

## Project status and future integration

The dashboard currently supports **offline post-mission analysis** of recorded mission telemetry and expected sensor measurements. Future integration with ROS 2 and actual onboard sensor streams would require additional data-export or live-connection functionality. The **Preflight (future)** tab is a placeholder; CSV validation alone does not establish that the AUV hardware is ready to deploy.
