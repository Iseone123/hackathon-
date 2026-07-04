"""Демо SQLite с экспериментами флотации для /ingest/sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROWS = [
    ("A1", 8.0, 0.5, 22, 78.2),
    ("A2", 8.5, 0.4, 23, 80.1),
    ("A3", 9.0, 0.3, 24, 84.5),
    ("A4", 9.5, 0.35, 25, 83.0),
    ("B1", 8.0, 0.6, 22, 76.5),
    ("B2", 9.0, 0.25, 24, 86.2),
    ("B3", 10.0, 0.3, 25, 81.0),
    ("C1", 8.5, 0.45, 23, 79.8),
]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    db_path = root / "data" / "experiments.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS flotation_experiments")
    conn.execute(
        """
        CREATE TABLE flotation_experiments (
            sample_id TEXT,
            pH REAL,
            reagent_dosage_kg_t REAL,
            temperature_C REAL,
            recovery_pct REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO flotation_experiments VALUES (?, ?, ?, ?, ?)",
        ROWS,
    )
    conn.commit()
    conn.close()
    print(f"Created {db_path} ({len(ROWS)} rows)")


if __name__ == "__main__":
    main()
