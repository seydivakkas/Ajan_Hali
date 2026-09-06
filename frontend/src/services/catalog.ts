export interface SupplierProduct {
  id: string; supplier: string; product_code: string; material: string;
  count_value: number; count_unit: 'dtex' | 'tex' | 'denier' | 'Nm';
  count_basis: 'FINISHED_YARN'; source_ref: string; dtex: number;
}
export interface MeasuredColor {
  id: string; product_id: string; color_code: string; name: string; dye_lot: string;
  lab: [number, number, number]; illuminant: 'D50' | 'D65' | 'A' | 'F11';
  observer: '2' | '10'; device: string; measured_at: string; source_ref: string;
}
export interface SupplierCatalog { products: SupplierProduct[]; colors: MeasuredColor[] }
export interface CatalogSnapshot { product: SupplierProduct; color: MeasuredColor | null }
const base = import.meta.env.VITE_API_URL || '';
async function read(res: Response): Promise<SupplierCatalog> {
  const body = await res.json();
  if (!res.ok) throw new Error(Array.isArray(body.detail)
    ? body.detail.map((e: any) => `${e.loc.join('.')}: ${e.msg}`).join('\n')
    : body.detail || 'Katalog işlemi başarısız.');
  return body;
}
export async function fetchCatalog() { return read(await fetch(`${base}/api/v1/catalog`)); }
export async function addCatalog(records: { products?: Omit<SupplierProduct, 'dtex'>[]; colors?: MeasuredColor[] }) {
  return read(await fetch(`${base}/api/v1/catalog`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(records) }));
}
export async function importCatalog(file: File) {
  const form = new FormData(); form.append('file', file);
  return read(await fetch(`${base}/api/v1/catalog/import`, {method:'POST', body:form}));
}
