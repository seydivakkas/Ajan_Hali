import { CatalogSnapshot } from './catalog';
export interface FactoryYarn {
  is_demo?: boolean;
  catalog_product_id?: string | null; catalog_color_id?: string | null;
  catalog_snapshot?: CatalogSnapshot | null;
  code: string; name: string; material: string; dtex: number | null;
  rgb: [number,number,number]; lab: [number | null,number | null,number | null];
  color_source: 'MEASURED_LAB' | 'RGB_ESTIMATE' | 'DEMO_SYNTHETIC';
  cost_per_kg_tl: number | null; bobbin_weight_kg: number | null; stock_kg: number | null;
}
export interface FactoryLoom { name: string; controller_model: string; ip: string | null; port: number | null; protocol: 'FTP' | 'SFTP' | 'SMB' | null }
export interface FactorySettings { revision: number; updated_at: string | null; company_name: string; erp_system: string; attio_company_record_id: string; yarns: FactoryYarn[]; looms: FactoryLoom[] }
const base = import.meta.env.VITE_API_URL || '';
async function response(res: Response) {
  if (!res.ok) { const body = await res.json().catch(() => ({})); const detail = body.detail;
    throw new Error(Array.isArray(detail) ? detail.map((e: any) => `${e.loc.join('.')}: ${e.msg}`).join('\n') : detail || 'Ayarlar kaydedilemedi.'); }
  return res.json();
}
export async function fetchSettings(): Promise<FactorySettings> { return response(await fetch(`${base}/api/v1/settings`)); }
export async function changeDemoInventory(revision: number, remove = false): Promise<FactorySettings> {
  return response(await fetch(`${base}/api/v1/demo/inventory`, {method:remove?'DELETE':'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({revision})}));
}
export async function deleteDemoJobs(): Promise<{removed:number}> {
  return response(await fetch(`${base}/api/v1/demo/jobs`, {method:'DELETE'}));
}
export async function putSettings(settings: FactorySettings): Promise<FactorySettings> { return response(await fetch(`${base}/api/v1/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) })); }
