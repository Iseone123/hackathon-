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
  structured_roadmap?: RoadmapStep[];
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

export interface RoadmapStep {
  step_order: number;
  title: string;
  description?: string;
  duration_days: number;
  resources: string[];
  success_criteria: string;
  failure_criteria: string;
  depends_on: number[];
}

export interface RoadmapTemplate {
  id: string;
  label: string;
  duration_days: number;
  resources: string[];
  cost_rub?: number;
}

export interface RoadmapSummary {
  hypothesis_id: string;
  steps: RoadmapStep[];
  total_days: number;
  step_count: number;
  estimated_cost_rub: number;
  resources_unique: string[];
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
const API_KEY = import.meta.env.VITE_API_KEY || '';

function apiHeaders(json = true): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h['Content-Type'] = 'application/json';
  if (API_KEY) h['X-API-Key'] = API_KEY;
  return h;
}

export async function generateHypotheses(
  problem: string,
  constraints: string,
  topK = 8,
  hypothesisCount = 5
): Promise<GenerateResponse> {
  const res = await fetch(`${API_URL}/hypotheses/generate`, {
    method: 'POST',
    headers: apiHeaders(),
    body: JSON.stringify({
      problem,
      constraints,
      top_k: topK,
      language: 'ru',
      hypothesis_count: hypothesisCount,
    }),
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
    headers: apiHeaders(),
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

export async function fetchRoadmapTemplates(): Promise<RoadmapTemplate[]> {
  const res = await fetch(`${API_URL}/roadmap/templates`, { headers: apiHeaders(false) });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.templates;
}

export async function fetchRoadmapSummary(hypothesisId: string): Promise<RoadmapSummary> {
  const res = await fetch(`${API_URL}/roadmap/${hypothesisId}/summary`, {
    headers: apiHeaders(false),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateRoadmap(
  hypothesisId: string,
  steps: RoadmapStep[]
): Promise<Hypothesis> {
  const res = await fetch(`${API_URL}/hypotheses/${hypothesisId}/roadmap`, {
    method: 'PATCH',
    headers: apiHeaders(),
    body: JSON.stringify({ steps }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
