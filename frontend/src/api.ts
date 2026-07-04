export interface CaseCheckItem {
  key: string;
  label: string;
  required: boolean;
  passed: boolean;
  note?: string;
}

export interface JudgeVerdict {
  approved: boolean;
  overall_score: number;
  testability: number;
  evidence_quality: number;
  relevance: number;
  source_grounded: boolean;
  objective_score: number;
  issues: string[];
  recommendations: string[];
  decision_rationale: string[];
  case_compliance?: {
    mandatory_passed: number;
    mandatory_total: number;
    compliance_pct: number;
    items: CaseCheckItem[];
  };
}

export interface JudgeSummary {
  jqi: number;
  approved: number;
  total: number;
  grounding_rate: number;
  avg_case_compliance_pct: number;
  objective_target: number;
}

export interface SourceRef {
  doc_id: string;
  snippet: string;
  url?: string;
}

export interface RiskScores {
  technical: number;
  economic: number;
}

export interface ScoreBreakdown {
  novelty: number;
  feasibility: number;
  expected_value: number;
  risk_inverted: number;
  novelty_vector?: number;
  novelty_llm?: number;
  weights: Record<string, number>;
  composite: number;
}

export interface Hypothesis {
  id: string;
  text: string;
  mechanism: string;
  novelty_score: number;
  feasibility_score: number;
  expected_value_score: number;
  risk: RiskScores;
  sources: SourceRef[];
  verification_roadmap?: string[];
  reasoning: string;
  conflicts: string[];
  influence_graph: {
    nodes?: Array<{ id: string; type: string; source_doc_id?: string; phase_order?: number }>;
    links?: Array<{ source: string; target: string; type: string }>;
    states?: Array<{ id: string; type: string; phase_order?: number; description?: string }>;
    transitions?: Array<{ from?: string; to?: string; source?: string; target?: string; type: string; condition?: string }>;
  };
  score_breakdown?: ScoreBreakdown;
  judge_verdict?: JudgeVerdict;
  generation_id?: string;
}

export interface GenerateResponse {
  generation_id: string;
  problem: string;
  constraints: string;
  hypotheses: Hypothesis[];
  conflicts_detected: string[];
  retrieval_doc_ids: string[];
  judge_summary?: JudgeSummary;
}

export interface DemoExample {
  id: string;
  name: string;
  data_path: string;
  problem: string;
  constraints: string;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function generateHypotheses(
  problem: string,
  constraints: string,
  topK = 8
): Promise<GenerateResponse> {
  const res = await fetch(`${API_URL}/hypotheses/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problem, constraints, top_k: topK }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadDocument(file: File, metadata: Record<string, unknown> = {}) {
  const form = new FormData();
  form.append('file', file);
  form.append('metadata', JSON.stringify(metadata));
  const res = await fetch(`${API_URL}/ingest`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function ingestBatch(directory: string) {
  const res = await fetch(`${API_URL}/ingest/batch?directory=${encodeURIComponent(directory)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchDemoExamples(): Promise<DemoExample[]> {
  const res = await fetch(`${API_URL}/demo/examples`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.examples;
}

export async function submitFeedback(
  hypothesisId: string,
  status: 'confirmed' | 'rejected' | 'needs_review',
  comment = ''
) {
  const res = await fetch(`${API_URL}/hypotheses/${hypothesisId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, comment }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function exportReportUrl(generationId: string, format: 'pdf' | 'docx') {
  return `${API_URL}/export/report?generation_id=${generationId}&format=${format}`;
}

export function exportTasksUrl(generationId: string, format: 'json' | 'csv') {
  return `${API_URL}/export/tasks?generation_id=${generationId}&format=${format}`;
}
