import { useCallback, useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  DemoExample,
  GenerateResponse,
  Hypothesis,
  exportReportUrl,
  exportTasksUrl,
  fetchDemoExamples,
  generateHypotheses,
  ingestBatch,
  submitFeedback,
  uploadDocument,
} from './api';

function InfluenceGraph({ graph }: { graph: Hypothesis['influence_graph'] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(400);

  useEffect(() => {
    if (containerRef.current) {
      setWidth(containerRef.current.offsetWidth);
    }
  }, []);

  const nodes = (graph?.nodes || []).map((n) => ({
    id: n.id,
    name: n.id,
    type: n.type,
  }));
  const links = (graph?.links || []).map((l) => ({
    source: l.source,
    target: l.target,
    type: l.type,
  }));

  if (!nodes.length) {
    return <p style={{ color: '#888', fontSize: '0.85rem' }}>Граф влияния не задан</p>;
  }

  return (
    <div ref={containerRef} className="graph-container">
      <ForceGraph2D
        graphData={{ nodes, links }}
        width={width}
        height={300}
        nodeLabel="name"
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = (node as { name?: string }).name || '';
          const fontSize = 12 / globalScale;
          ctx.font = `${fontSize}px Sans-Serif`;
          const color =
            (node as { type?: string }).type === 'Material'
              ? '#2563eb'
              : (node as { type?: string }).type === 'Process'
                ? '#16a34a'
                : '#9333ea';
          ctx.beginPath();
          ctx.arc(node.x!, node.y!, 5, 0, 2 * Math.PI, false);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = '#333';
          ctx.fillText(label, node.x!, node.y! + 10);
        }}
      />
    </div>
  );
}

export default function App() {
  const [problem, setProblem] = useState('');
  const [constraints, setConstraints] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [selected, setSelected] = useState<Hypothesis | null>(null);
  const [examples, setExamples] = useState<DemoExample[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchDemoExamples().then(setExamples).catch(() => {});
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!problem.trim()) {
      setError('Укажите целевую проблему');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await generateHypotheses(problem, constraints);
      setResult(res);
      setSelected(res.hypotheses[0] || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка генерации');
    } finally {
      setLoading(false);
    }
  }, [problem, constraints]);

  const loadExample = async (ex: DemoExample) => {
    setProblem(ex.problem);
    setConstraints(ex.constraints);
    setLoading(true);
    setError('');
    try {
      await ingestBatch(ex.data_path);
      const res = await generateHypotheses(ex.problem, ex.constraints);
      setResult(res);
      setSelected(res.hypotheses[0] || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка демо-сценария');
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      await uploadDocument(file, { title: file.name });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>Генерация научных гипотез</h1>
        <p>RAG + граф знаний + YandexGPT — материаловедение и металлургия</p>
      </header>

      <div className="grid">
        <div>
          <div className="panel">
            <h2>Запрос</h2>
            <label>Целевая проблема</label>
            <textarea
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
              placeholder="Например: повышение извлечения меди из хвостов..."
            />
            <label>Ограничения</label>
            <textarea
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              placeholder="Бюджет, TRL, оборудование..."
            />
            <button onClick={handleGenerate} disabled={loading}>
              {loading ? 'Генерация...' : 'Сгенерировать гипотезы'}
            </button>
          </div>

          <div className="panel" style={{ marginTop: 16 }}>
            <h2>Данные</h2>
            <label>Загрузить документ (PDF/DOCX/XLSX/TXT)</label>
            <input type="file" onChange={handleUpload} disabled={uploading} />
            {examples.length > 0 && (
              <>
                <label style={{ marginTop: 12 }}>Демо-примеры</label>
                {examples.map((ex) => (
                  <button
                    key={ex.id}
                    className="secondary"
                    onClick={() => loadExample(ex)}
                    disabled={loading}
                  >
                    {ex.name}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>

        <div>
          {error && <div className="error">{error}</div>}

          {loading && <div className="loading">Генерация гипотез (1-3 мин)...</div>}

          {result && !loading && (
            <>
              {result.conflicts_detected.length > 0 && (
                <div className="conflicts">
                  <strong>Обнаружены противоречия в источниках:</strong>
                  <ul>
                    {result.conflicts_detected.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.judge_summary && (
                <div className="panel" style={{ marginBottom: 16 }}>
                  <h2>Качество прогона (JQI)</h2>
                  <div className="scores">
                    <span>JQI: {result.judge_summary.jqi.toFixed(1)}</span>
                    <span>
                      Одобрено: {result.judge_summary.approved}/{result.judge_summary.total}
                    </span>
                    <span>
                      RAG: {(result.judge_summary.grounding_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              )}

              <div className="panel">
                <h2>
                  Гипотезы ({result.hypotheses.length})
                  <span className="badge" style={{ marginLeft: 8 }}>
                    {result.generation_id.slice(0, 8)}
                  </span>
                </h2>

                {result.hypotheses.map((h) => {
                  const jv = h.judge_verdict;
                  const approved = jv?.approved;
                  return (
                  <div
                    key={h.id}
                    className={`hypothesis-card ${selected?.id === h.id ? 'selected' : ''}`}
                    onClick={() => setSelected(h)}
                  >
                    <h3>
                      {approved === true && <span className="badge ok">✓</span>}
                      {approved === false && <span className="badge reject">✗</span>}
                      {h.text}
                    </h3>
                    <div className="scores">
                      {jv && <span>Судья: {jv.overall_score.toFixed(1)}</span>}
                      <span>Score: {(h.score_breakdown?.composite ?? 0).toFixed(3)}</span>
                      <span>Новизна: {h.novelty_score}</span>
                      <span>Реализуемость: {h.feasibility_score}</span>
                      <span>Ценность: {h.expected_value_score}</span>
                      <span>Риск: {h.risk.technical}/{h.risk.economic}</span>
                    </div>
                  </div>
                  );
                })}

                <div style={{ marginTop: 12 }}>
                  <a href={exportReportUrl(result.generation_id, 'pdf')} target="_blank" rel="noreferrer">
                    <button className="secondary">PDF</button>
                  </a>
                  <a href={exportReportUrl(result.generation_id, 'docx')} target="_blank" rel="noreferrer">
                    <button className="secondary">DOCX</button>
                  </a>
                  <a href={exportTasksUrl(result.generation_id, 'json')} target="_blank" rel="noreferrer">
                    <button className="secondary">JSON задачи</button>
                  </a>
                  <a href={exportTasksUrl(result.generation_id, 'csv')} target="_blank" rel="noreferrer">
                    <button className="secondary">CSV</button>
                  </a>
                </div>
              </div>

              {selected && (
                <div className="panel" style={{ marginTop: 16 }}>
                  <h2>Детали гипотезы</h2>
                  {selected.judge_verdict && (
                    <div
                      className={
                        selected.judge_verdict.approved
                          ? 'judge-box approved'
                          : 'judge-box rejected'
                      }
                    >
                      <strong>
                        {selected.judge_verdict.approved
                          ? 'Почему судья одобрил'
                          : 'Почему судья отклонил'}
                      </strong>
                      <ul>
                        {(selected.judge_verdict.decision_rationale?.length
                          ? selected.judge_verdict.decision_rationale
                          : selected.judge_verdict.issues
                        ).map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ul>
                      <p className="hint">
                        «Обоснование» ниже — аргумент модели при генерации, не вердикт судьи.
                      </p>
                    </div>
                  )}
                  <p><strong>Механизм:</strong> {selected.mechanism}</p>
                  <p><strong>Обоснование генератора:</strong> {selected.reasoning}</p>
                  {selected.score_breakdown && (
                    <div className="scores" style={{ marginBottom: 12 }}>
                      <span>novelty_vec: {selected.score_breakdown.novelty_vector ?? '—'}</span>
                      <span>novelty_llm: {selected.score_breakdown.novelty_llm}</span>
                      <span>feasibility: {selected.score_breakdown.feasibility}</span>
                      <span>value: {selected.score_breakdown.expected_value}</span>
                      <span>risk_inv: {selected.score_breakdown.risk_inverted}</span>
                    </div>
                  )}
                  <h3 style={{ fontSize: '0.95rem' }}>Граф влияния</h3>
                  <InfluenceGraph graph={selected.influence_graph} />
                  {selected.sources.length > 0 && (
                    <div className="sources">
                      <strong>Источники:</strong>
                      {selected.sources.map((s, i) => (
                        <div key={i}>
                          [{s.doc_id}] {s.snippet.slice(0, 150)}...
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ marginTop: 12 }}>
                    <button
                      className="secondary"
                      onClick={() => submitFeedback(selected.id, 'confirmed')}
                    >
                      Подтвердить
                    </button>
                    <button
                      className="secondary"
                      onClick={() => submitFeedback(selected.id, 'rejected')}
                    >
                      Отклонить
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
