"""Визуализация дорожной карты (Gantt-подобная шкала)."""

from __future__ import annotations

from typing import Any


def render_roadmap_timeline_html(timeline: list[dict[str, Any]], total_days: int) -> str:
    if not timeline:
        return ""
    max_end = max(t["end_day"] for t in timeline) or total_days or 1
    rows: list[str] = []
    for item in timeline:
        left_pct = 100 * item["start_day"] / max_end
        width_pct = max(8, 100 * item["duration_days"] / max_end)
        rows.append(
            f"""
            <div style="margin-bottom:10px;">
              <div style="font-size:12px;margin-bottom:4px;">
                <b>Шаг {item['step']}</b>: {item['title']}
                <span style="color:#64748b;"> ({item['duration_days']} дн.)</span>
              </div>
              <div style="background:#e2e8f0;border-radius:6px;height:22px;position:relative;">
                <div style="position:absolute;left:{left_pct:.1f}%;width:{width_pct:.1f}%;
                     background:#2563eb;border-radius:6px;height:22px;"></div>
              </div>
              <div style="font-size:11px;color:#475569;margin-top:2px;">
                Ресурсы: {item.get('resources', '')}
              </div>
            </div>
            """
        )
    return f"""
    <div style="font-family:system-ui;padding:8px;">
      <div style="font-weight:600;margin-bottom:8px;">Дорожная карта ({max_end} дн.)</div>
      {''.join(rows)}
    </div>
    """
