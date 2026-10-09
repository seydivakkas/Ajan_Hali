import { apiFetch } from './auth';
import { AnalysisPipelineResult, LoomFormConfig } from '../types/carpet';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export async function checkBackendHealth(): Promise<{ status: string; engine: string }> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function runCarpetAnalysis(
  file: File,
  config: LoomFormConfig
): Promise<AnalysisPipelineResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('manual_corners', JSON.stringify(config.manual_corners || null));
  formData.append('repair_regions', JSON.stringify(config.repair_regions || []));
  formData.append('weave_structure_factor', config.weave_structure_factor.toString());
  formData.append('anchor_length_mm', config.anchor_length_mm.toString());
  formData.append('width_cm', config.width_cm.toString());
  formData.append('length_cm', config.length_cm.toString());
  formData.append('reed_density', config.reed_density.toString());
  formData.append('pick_density', config.pick_density.toString());
  formData.append('pile_height_mm', config.pile_height_mm.toString());
  formData.append('max_colors', config.max_colors.toString());
  formData.append('order_quantity', config.order_quantity.toString());
  formData.append('waste_coefficient', config.waste_coefficient.toString());
  formData.append('enable_symmetry', config.enable_symmetry.toString());
  formData.append('enable_sam', config.enable_sam.toString());
  formData.append('enable_dereflection', config.enable_dereflection.toString());
  formData.append('symmetry_mode', config.symmetry_mode);

  const res = await apiFetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(Array.isArray(err.detail) ? err.detail.map((e: any) => `${e.loc.join('.')}: ${e.msg}`).join('; ') : err.detail || 'Analiz sırasında hata oluştu.');
  }

  return res.json();
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
  // Normalize Windows backslashes
  const normalized = path.replace(/\\/g, '/');
  // If it contains "output/", strip the leading parts before output
  const outputIdx = normalized.indexOf('output/');
  if (outputIdx !== -1) {
    return `${API_BASE_URL}/static/${normalized.substring(outputIdx + 7)}`;
  }
  // Otherwise return as is
  return `${API_BASE_URL}/${normalized}`;
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
