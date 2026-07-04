"""Создаёт data/Лабораторные опыты.xlsx — демо-таблица лабораторных опытов."""

from __future__ import annotations

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
    from openpyxl import Workbook

    root = Path(__file__).resolve().parents[2]
    out = root / "data" / "Лабораторные опыты.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Опыты"
    ws.append(
        ["sample_id", "pH", "reagent_dosage_kg_t", "temperature_C", "recovery_pct"]
    )
    for row in ROWS:
        ws.append(list(row))
    wb.save(out)
    print(f"Created {out} ({len(ROWS)} experiments)")


if __name__ == "__main__":
    main()
