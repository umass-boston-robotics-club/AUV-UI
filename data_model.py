"""CSV schema validation and mission calculations (no GUI dependencies)."""

from dataclasses import dataclass
from pathlib import Path

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
        Raises ValueError if the file cannot be read or its contents are invalid."""
        
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
