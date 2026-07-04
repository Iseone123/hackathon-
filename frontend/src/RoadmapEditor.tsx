import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RoadmapStep,
  RoadmapSummary,
  RoadmapTemplate,
  fetchRoadmapSummary,
  fetchRoadmapTemplates,
  updateRoadmap,
} from './api';

interface Props {
  hypothesisId: string;
  onUpdated?: (steps: RoadmapStep[]) => void;
}

function estimateCost(steps: RoadmapStep[]): number {
  return steps.reduce((sum, s) => {
    const base = 15_000 * Math.max(1, Math.floor(s.duration_days / 7));
    return sum + base + 8_000 * (s.resources?.length || 0);
  }, 0);
}

function timelineFromSteps(steps: RoadmapStep[]) {
  const ordered = [...steps].sort((a, b) => a.step_order - b.step_order);
  let cursor = 0;
  return ordered.map((s) => {
    const start = cursor;
    cursor += s.duration_days;
    return { step: s.step_order, title: s.title, start, end: cursor, duration: s.duration_days };
  });
}

export default function RoadmapEditor({ hypothesisId, onUpdated }: Props) {
  const [steps, setSteps] = useState<RoadmapStep[]>([]);
  const [templates, setTemplates] = useState<RoadmapTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selectedTpl, setSelectedTpl] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [summary, tpls] = await Promise.all([
        fetchRoadmapSummary(hypothesisId),
        fetchRoadmapTemplates(),
      ]);
      setSteps(summary.steps || []);
      setTemplates(tpls);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки roadmap');
    } finally {
      setLoading(false);
    }
  }, [hypothesisId]);

  useEffect(() => {
    load();
  }, [load]);

  const timeline = useMemo(() => timelineFromSteps(steps), [steps]);
  const totalDays = timeline.length ? timeline[timeline.length - 1].end : 0;
  const totalCost = estimateCost(steps);

  const moveStep = (index: number, direction: -1 | 1) => {
    const next = [...steps];
    const j = index + direction;
    if (j < 0 || j >= next.length) return;
    [next[index], next[j]] = [next[j], next[index]];
    next.forEach((s, i) => {
      s.step_order = i + 1;
      s.depends_on = i > 0 ? [i] : [];
    });
    setSteps(next);
  };

  const removeStep = (index: number) => {
    const next = steps.filter((_, i) => i !== index);
    next.forEach((s, i) => {
      s.step_order = i + 1;
      s.depends_on = i > 0 ? [i] : [];
    });
    setSteps(next);
  };

  const addFromTemplate = () => {
    const tpl = templates.find((t) => t.id === selectedTpl);
    if (!tpl) return;
    const order = steps.length + 1;
    setSteps([
      ...steps,
      {
        step_order: order,
        title: tpl.label,
        description: tpl.label,
        duration_days: tpl.duration_days,
        resources: [...tpl.resources],
        success_criteria: 'Улучшение KPI ≥3% vs контроль',
        failure_criteria: 'Нет значимого эффекта vs контроль',
        depends_on: order > 1 ? [order - 1] : [],
      },
    ]);
  };

  const updateStep = (index: number, patch: Partial<RoadmapStep>) => {
    setSteps(steps.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const updated = await updateRoadmap(hypothesisId, steps);
      setSteps(updated.structured_roadmap || steps);
      onUpdated?.(updated.structured_roadmap || steps);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="hint">Загрузка конструктора roadmap…</p>;
  if (error && !steps.length) return <p className="error">{error}</p>;

  return (
    <div className="roadmap-editor">
      <h3>Конструктор дорожной карты</h3>
      <div className="scores" style={{ marginBottom: 12 }}>
        <span>Срок: {totalDays} дн.</span>
        <span>Шагов: {steps.length}</span>
        <span>Бюджет: {totalCost.toLocaleString('ru-RU')} ₽</span>
      </div>

      <div className="roadmap-gantt">
        {timeline.map((t) => (
          <div key={t.step} className="gantt-row">
            <div className="gantt-label">
              Шаг {t.step}: {t.title.slice(0, 36)}
              <span className="hint"> ({t.duration} дн.)</span>
            </div>
            <div className="gantt-track">
              <div
                className="gantt-bar"
                style={{
                  marginLeft: `${(100 * t.start) / Math.max(totalDays, 1)}%`,
                  width: `${Math.max(8, (100 * t.duration) / Math.max(totalDays, 1))}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, margin: '12px 0', flexWrap: 'wrap' }}>
        <select value={selectedTpl} onChange={(e) => setSelectedTpl(e.target.value)}>
          <option value="">— шаблон шага —</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label} ({t.duration_days} дн.)
            </option>
          ))}
        </select>
        <button type="button" className="secondary" onClick={addFromTemplate} disabled={!selectedTpl}>
          Добавить
        </button>
        <button type="button" onClick={save} disabled={saving}>
          {saving ? 'Сохранение…' : 'Сохранить roadmap'}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {steps.map((step, i) => (
        <div key={step.step_order} className="roadmap-step-card">
          <div className="roadmap-step-header">
            <strong>Шаг {step.step_order}</strong>
            <div>
              <button type="button" className="secondary" onClick={() => moveStep(i, -1)} disabled={i === 0}>
                ↑
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => moveStep(i, 1)}
                disabled={i >= steps.length - 1}
              >
                ↓
              </button>
              <button type="button" className="secondary" onClick={() => removeStep(i)}>
                ✕
              </button>
            </div>
          </div>
          <label>Название</label>
          <input
            value={step.title}
            onChange={(e) => updateStep(i, { title: e.target.value, description: e.target.value })}
          />
          <label>Длительность (дн.): {step.duration_days}</label>
          <input
            type="range"
            min={1}
            max={90}
            value={step.duration_days}
            onChange={(e) => updateStep(i, { duration_days: Number(e.target.value) })}
          />
          <label>Ресурсы (через запятую)</label>
          <input
            value={(step.resources || []).join(', ')}
            onChange={(e) =>
              updateStep(i, {
                resources: e.target.value.split(',').map((r) => r.trim()).filter(Boolean),
              })
            }
          />
          <label>Критерий успеха</label>
          <input
            value={step.success_criteria}
            onChange={(e) => updateStep(i, { success_criteria: e.target.value })}
          />
          <label>Критерий провала</label>
          <input
            value={step.failure_criteria}
            onChange={(e) => updateStep(i, { failure_criteria: e.target.value })}
          />
        </div>
      ))}
    </div>
  );
}
