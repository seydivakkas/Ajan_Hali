import { apiFetch } from './auth';
import { AnalysisPipelineResult, LoomFormConfig } from '../types/carpet';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export async function checkBackendHealth(): Promise<{ status: string; engine: string }> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export interface AnalysisJobStatus {
  job_id: string;
  state: 'QUEUED' | 'RUNNING' | 'CANCEL_REQUESTED' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
  stage: string;
  percent: number;
  error_code: string | null;
  cancel_requested: boolean;
}

async function parseApiError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return Array.isArray(body.detail)
    ? body.detail.map((item: {loc?: string[], msg: string}) => item.msg).join('; ')
    : body.detail || `HTTP ${response.status}`;
}

export async function cancelQueuedAnalysis(jobId: string): Promise<AnalysisJobStatus> {
  const response = await apiFetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}

export async function runCarpetAnalysis(
  file: File,
  config: LoomFormConfig,
  onProgress?: (status: AnalysisJobStatus) => void
): Promise<AnalysisPipelineResult> {
  // Every user-initiated submission has a unique idempotency key. The server
  // binds it to a digest of the actual photo, config and company revision.
  const requestBody = new FormData();
  requestBody.append('file', file);
  requestBody.append('config', JSON.stringify({
    idempotency_key: crypto.randomUUID().replaceAll('-', ''),
    loom_config: {
      weave_structure_factor: config.weave_structure_factor,
      anchor_length_mm: config.anchor_length_mm,
      width_cm: config.width_cm,
      length_cm: config.length_cm,
      reed_density: config.reed_density,
      pick_density: config.pick_density,
      pile_height_mm: config.pile_height_mm,
      max_colors: config.max_colors,
      order_quantity: config.order_quantity,
      waste_coefficient: config.waste_coefficient,
    },
    preprocessing_config: {
      manual_corners: config.manual_corners || null,
      repair_regions: config.repair_regions || [],
      enable_symmetry_completion: config.enable_symmetry,
      enable_sam_segmentation: config.enable_sam,
      enable_dereflection: config.enable_dereflection,
      symmetry_mode: config.symmetry_mode,
    },
  }));

  const response = await apiFetch(`${API_BASE_URL}/api/v1/analyze/jobs`, {
    method: 'POST', body: requestBody,
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  let status: AnalysisJobStatus = await response.json();
  onProgress?.(status);
  const deadline = Date.now() + 15 * 60 * 1000;
  for (;;) {
    if (status.state === 'SUCCEEDED') return fetchJob(status.job_id);
    if (status.state === 'FAILED' || status.state === 'CANCELLED') {
      throw new Error(`Analiz ${status.state}: ${status.error_code || status.stage}. Tekrar için yeni bir işlem başlatın.`);
    }
    if (Date.now() > deadline) {
      throw new Error(`Analiz zaman aşımına uğradı. İş ${status.job_id} sunucuda izlenmeye devam ediyor.`);
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
    const update = await apiFetch(
      `${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(status.job_id)}/status`);
    if (!update.ok) throw new Error(await parseApiError(update));
    status = await update.json();
    onProgress?.(status);
  }
}

export function getDownloadUrl(jobId: string, fileType: 'dxf' | 'svg' | 'loom' | 'vdw' | 'staubli' | 'report'): string {
  return `${API_BASE_URL}/api/v1/jobs/${jobId}/download/${fileType}`;
}

export async function fetchERPInventory(): Promise<any> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/erp/inventory`);
  if (!res.ok) throw new Error('ERP Envanteri alınamadı');
  return res.json();
}

export async function uploadSpectroFile(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('register_palette', 'true');
  const res = await apiFetch(`${API_BASE_URL}/api/v1/spectro/import`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) throw new Error('Spektrofotometre dosyası okunamadı');
  return res.json();
}

export function resolveImageUrl(path: string | undefined | null): string {
  if (!path) return '';
  // The server scopes /static requests to the authenticated company.
  // Never include output/workspaces/<tenant> in the client URL: it isn't
  // a security selector and legacy outputs have different root layouts.
  const segments = path.replace(/\\/g, '/').split('/');
  const fileName = segments[segments.length - 1];
  const jobId = segments[segments.length - 2];
  if (!jobId || !/^[A-Za-z0-9_-]{1,80}$/.test(jobId) ||
      !/^[A-Za-z0-9_.-]{1,120}$/.test(fileName)) return '';
  return `${API_BASE_URL}/static/${encodeURIComponent(jobId)}/${encodeURIComponent(fileName)}`;
}

export interface JobSummary {
  data_source?: string;
  job_id: string;
  created_at?: string;
  dimensions: [number, number];
  status: string;
  cost_tl: number;
}
export async function fetchJobs(): Promise<JobSummary[]> {
  const response = await apiFetch(`${API_BASE_URL}/api/v1/jobs`);
  if (!response.ok) throw new Error('Analiz geçmişi alınamadı.');
  return response.json();
}
export async function fetchJob(id: string): Promise<AnalysisPipelineResult> {
  const response = await apiFetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('Analiz açılamadı.');
  return response.json();
}

export interface DesignReview { id: string; reviewer: string; decision: 'DESIGN_ACCEPTED' | 'CHANGES_REQUESTED'; note: string; created_at: string; report_sha256: string }
export async function fetchReviews(jobId: string): Promise<DesignReview[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}/reviews`);
  if (!res.ok) throw new Error('İnceleme kayıtları yüklenemedi.');
  return res.json();
}
export async function saveReview(jobId: string, review: Pick<DesignReview, 'reviewer' | 'decision' | 'note'>): Promise<DesignReview> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}/reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(review) });
  if (!res.ok) throw new Error('İnceleme kaydedilemedi. Ad ve açıklamayı kontrol edin.');
  return res.json();
}
