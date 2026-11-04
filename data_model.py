"""CSV schema validation and mission/sensor calculations (no GUI dependencies)."""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "elapsed_sim_s",
    "phase",
    "x_m",
    "y_m",
    "z_m",
    "heading_deg",
    "command_thrust_N",
    "command_rudder_rad",
)
NUMERIC_COLUMNS = tuple(col for col in REQUIRED_COLUMNS if col != "phase")


@dataclass
class MissionData:
    """A validated mission CSV and its derived metrics."""

    path: Path
    frame: pd.DataFrame

    @classmethod
    def from_csv(cls, filepath: str | Path) -> "MissionData":
        """Read a CSV, validate required mission fields, and return normalized data.

        Raises ValueError if the file cannot be read or its contents are invalid.
        """
        path = Path(filepath)

        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeError) as exc:
            raise ValueError(f"Could not read CSV: {exc}") from exc

        if frame.empty:
            raise ValueError("The CSV has no mission samples.")

        missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(missing))

        frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
        for name in NUMERIC_COLUMNS:
            try:
                frame[name] = pd.to_numeric(frame[name], errors="raise")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Column '{name}' must contain numbers.") from exc

            # Reject missing, NaN, and infinite numeric values.
            if not np.isfinite(frame[name].to_numpy(dtype=float)).all():
                raise ValueError(f"Column '{name}' contains missing or infinite values.")

        if frame["phase"].isna().any():
            raise ValueError("The phase column contains missing values.")
        frame["phase"] = frame["phase"].astype(str).str.strip()
        if frame["phase"].eq("").any():
            raise ValueError("The phase column contains empty labels.")

        # Row order is chronological; a repeated/descending timestamp is invalid.
        if (frame["elapsed_sim_s"].diff().iloc[1:] <= 0).any():
            raise ValueError("elapsed_sim_s must increase strictly from one row to the next.")

        return cls(path=path, frame=frame.reset_index(drop=True))

    @property
    def duration_s(self) -> float:
        t = self.frame["elapsed_sim_s"]
        return float(t.iloc[-1] - t.iloc[0])

    @property
    def distance_m(self) -> float:
        """Cumulative 3D distance between consecutive recorded positions."""
        xyz = self.frame[["x_m", "y_m", "z_m"]].to_numpy(dtype=float)
        if len(xyz) <= 1:
            return 0.0
        return float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum())

    @property
    def phases(self) -> list[str]:
        """Return distinct phase labels in order of first appearance."""
        return self.frame["phase"].drop_duplicates().tolist()

    @property
    def z_range_m(self) -> tuple[float, float]:
        z = self.frame["z_m"]
        return float(z.min()), float(z.max())

    def subset(self, phase: str | None = None) -> pd.DataFrame:
        """Return all samples or only those matching a phase."""
        if phase is None:
            return self.frame
        return self.frame.loc[self.frame["phase"] == phase].reset_index(drop=True)


# Common sensor header spellings; all time columns must contain elapsed seconds.
SENSOR_COLUMN_ALIASES = {
    "time_s": ("time_s", "time", "elapsed_sim_s", "elapsed_s", "timestamp_s", "seconds", "t_s"),
    "temperature_c": ("temperature_c", "temperature", "temp_c", "temp", "water_temperature_c"),
    "ph": ("ph", "p_h", "water_ph"),
    "voltage_v": ("voltage_v", "voltage", "battery_voltage_v", "battery_voltage", "battery_v"),
    "depth_m": ("depth_m", "depth", "water_depth_m"),
}


def _normalize_column_name(name: str) -> str:
    """Normalize CSV headers such as 'Temperature (C)' to 'temperaturec'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@dataclass
class SensorData:
    """Validated offline sensor measurements, with optional measured depth."""

    path: Path
    frame: pd.DataFrame

    @classmethod
    def from_csv(cls, filepath: str | Path) -> "SensorData":
        path = Path(filepath)
        try:
            original = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeError) as exc:
            raise ValueError(f"Could not read sensor CSV: {exc}") from exc

        if original.empty:
            raise ValueError("The sensor CSV has no samples.")

        normalized = {}
        for col in original.columns:
            normalized.setdefault(_normalize_column_name(col), []).append(col)

        resolved = {}
        for canonical, aliases in SENSOR_COLUMN_ALIASES.items():
            candidates = {
                name
                for alias in aliases
                for name in normalized.get(_normalize_column_name(alias), [])
            }
            if len(candidates) > 1:
                raise ValueError(
                    f"Multiple CSV columns look like '{canonical}': " + ", ".join(sorted(candidates))
                )
            if candidates:
                resolved[canonical] = next(iter(candidates))

        required = ("time_s", "temperature_c", "ph", "voltage_v")
        missing = [key for key in required if key not in resolved]
        if missing:
            raise ValueError(
                "Missing sensor CSV fields: " + ", ".join(missing)
                + ". Expected time, temperature, pH and voltage (depth is optional)."
            )

        frame = pd.DataFrame()
        for key in (*required, "depth_m"):
            if key not in resolved:
                continue
            try:
                frame[key] = pd.to_numeric(original[resolved[key]], errors="raise")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Sensor column '{resolved[key]}' must contain numbers.") from exc
            if not np.isfinite(frame[key].to_numpy(dtype=float)).all():
                raise ValueError(f"Sensor column '{resolved[key]}' has missing or infinite values.")

        if (frame["time_s"].diff().iloc[1:] <= 0).any():
            raise ValueError("Sensor time must increase strictly; use elapsed seconds.")

        if "depth_m" in frame and (frame["depth_m"] < 0).any():
            raise ValueError("depth_m must be nonnegative: 0 means water surface.")

        return cls(path=path, frame=frame.reset_index(drop=True))

    @property
    def has_depth(self) -> bool:
        return "depth_m" in self.frame.columns

    def depth_for_profile(self, source: str = "csv", mission: MissionData | None = None) -> np.ndarray:
        """Get depth in meters (+down) for each sensor measurement.

        'csv': use recorded sensor depth_m.
        'mission_minus_z'/'mission_plus_z': interpolate mission Z at sensor times.
        Both CSVs MUST share the same elapsed-seconds clock. Mission Z=0 MUST
        mean the water surface, and the user must pick the correct Z sign.
        Never extrapolate outside mission timestamps.
        """
        if source == "csv":
            if not self.has_depth:
                raise ValueError(
                    "This sensor CSV has no depth column. Add depth_m, or load a mission CSV "
                    "with the same time reference and select a mission Z depth source."
                )
            return self.frame["depth_m"].to_numpy(dtype=float).copy()

        if source not in ("mission_minus_z", "mission_plus_z"):
            raise ValueError(f"Unknown depth source: {source}")
        if mission is None:
            raise ValueError("Load a mission CSV before using mission Z as the depth source.")

        mt = mission.frame["elapsed_sim_s"].to_numpy(dtype=float)
        mz = mission.frame["z_m"].to_numpy(dtype=float)
        st = self.frame["time_s"].to_numpy(dtype=float)
        if len(mt) < 2:
            raise ValueError("At least two mission timestamps are needed to interpolate depth.")

        depth = np.full(st.shape, np.nan)
        within = (st >= mt[0]) & (st <= mt[-1])
        depth[within] = np.interp(st[within], mt, mz)
        if source == "mission_minus_z":
            depth = -depth
        # No point beyond mission timing or above the declared water surface is usable.
        depth[depth < 0] = np.nan
        if np.count_nonzero(np.isfinite(depth)) < 2:
            raise ValueError(
                "Not enough valid matching depths. Check that sensor and mission time "
                "share the same seconds clock, and that mission Z=0 is the water surface "
                "with the selected sign."
            )
        return depth
