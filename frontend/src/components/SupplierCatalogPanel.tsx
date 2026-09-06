import React, { useState } from 'react';
import { SupplierCatalog, SupplierProduct, MeasuredColor, addCatalog, importCatalog } from '../services/catalog';

const style = 'w-full mt-1 rounded-lg bg-slate-950 border border-slate-700 p-2 text-sm';
const newProduct = () => ({ id:'', supplier:'', product_code:'', material:'', count_value:'', count_unit:'dtex', source_ref:'' });
const newColor = () => ({ id:'', product_id:'', color_code:'', name:'', dye_lot:'', l:'', a:'', b:'', illuminant:'', observer:'', device:'', measured_at:'', source_ref:'' });

export function SupplierCatalogPanel({catalog, onChange}: {catalog: SupplierCatalog; onChange: (catalog: SupplierCatalog) => void}) {
  const [product, setProduct] = useState(newProduct);
  const [color, setColor] = useState(newColor);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const run = async (operation: () => Promise<SupplierCatalog>, done?: () => void) => {
    setBusy(true); setMessage('');
    try { onChange(await operation()); done?.(); setMessage('Katalog kaydedildi. Envanter satırındaki seçimlerden kullanabilirsiniz.'); }
    catch(e: any) { setMessage(e.message); } finally { setBusy(false); }
  };
  const addProduct = () => {
    if (Object.values(product).some(v => !v.trim())) { setMessage('İplik kaydındaki tüm alanları doldurun.'); return; }
    const record = {...product, count_value:Number(product.count_value), count_unit:product.count_unit as SupplierProduct['count_unit'], count_basis:'FINISHED_YARN' as const};
    void run(() => addCatalog({products:[record]}), () => setProduct(newProduct()));
  };
  const addColor = () => {
    if (Object.values(color).some(v => !v.trim())) { setMessage('Kartela kaydındaki tüm alanları doldurun.'); return; }
    const {l,a,b,...rest} = color;
    const record = {...rest, lab:[Number(l),Number(a),Number(b)] as [number,number,number], illuminant:color.illuminant as MeasuredColor['illuminant'], observer:color.observer as MeasuredColor['observer']};
    void run(() => addCatalog({colors:[record]}), () => setColor(newColor()));
  };
  return <section className="p-4 rounded-xl border border-sky-900 bg-slate-900 space-y-4">
    <h3 className="font-semibold">Tedarikçi kataloğu ve ölçümlü kartela</h3>
    <p className="text-xs text-slate-400">{catalog.products.length} iplik ürünü · {catalog.colors.length} ölçümlü renk. Kaynak belgeyi veya bağlantısını girin. Katalog eklemek envanter, fiyat veya stok oluşturmaz.</p>
    <fieldset disabled={busy} className="space-y-4">
      <label className="text-xs block">JSON kataloğu içe aktar (en fazla 2 MB)
        <input type="file" accept=".json" className="block mt-2" onChange={e => {const file=e.target.files?.[0]; e.target.value=''; if(file) void run(() => importCatalog(file));}} />
      </label>
      <details className="border-t border-slate-700 pt-3">
        <summary className="cursor-pointer text-sm">+ Tedarikçi ipliği tanımla</summary>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
          {([['id','Katalog kayıt kimliği'],['supplier','Tedarikçi'],['product_code','Tedarikçi ürün kodu'],['material','Malzeme'],['source_ref','Kaynak belge / URL']] as const).map(([key,label]) => <label key={key} className="text-xs">{label}<input className={style} value={product[key]} onChange={e=>setProduct({...product,[key]:e.target.value})}/></label>)}
          <label className="text-xs">İplik numarası<input type="number" min="0.000001" step="any" className={style} value={product.count_value} onChange={e=>setProduct({...product,count_value:e.target.value})}/></label>
          <label className="text-xs">Numara birimi<select className={style} value={product.count_unit} onChange={e=>setProduct({...product,count_unit:e.target.value})}><option>dtex</option><option>tex</option><option>denier</option><option>Nm</option></select></label>
        </div>
        <p className="text-xs text-slate-400 mt-3">Numara, dokumada kullanılacak bitmiş ipliğin toplam numarası olmalıdır. Tek kat numarasını kat sayısıyla doğrulamadan kullanmayın.</p>
        <button type="button" className="mt-3 rounded-lg px-3 py-2 bg-sky-700 text-sm" onClick={addProduct}>İplik kaydını kataloğa ekle</button>
      </details>
      <details className="border-t border-slate-700 pt-3">
        <summary className="cursor-pointer text-sm">+ Ölçümlü kartela / boya partisi tanımla</summary>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
          <label className="text-xs">Ait olduğu tedarikçi ipliği<select className={style} value={color.product_id} onChange={e=>setColor({...color,product_id:e.target.value})}><option value="">Seçin…</option>{catalog.products.map(p=><option key={p.id} value={p.id}>{p.supplier} / {p.product_code}</option>)}</select></label>
          {([['id','Kartela kayıt kimliği'],['color_code','Kartela renk kodu'],['name','Ölçülen renk adı'],['dye_lot','Boya parti kodu'],['device','Ölçüm cihazı'],['source_ref','Ölçüm raporu / URL']] as const).map(([key,label])=><label key={key} className="text-xs">{label}<input className={style} value={color[key]} onChange={e=>setColor({...color,[key]:e.target.value})}/></label>)}
          {(['l','a','b'] as const).map(key=><label key={key} className="text-xs">{key==='l'?'L*':key+'*'}<input type="number" step="any" className={style} value={color[key]} onChange={e=>setColor({...color,[key]:e.target.value})}/></label>)}
          <label className="text-xs">Aydınlatıcı<select className={style} value={color.illuminant} onChange={e=>setColor({...color,illuminant:e.target.value})}><option value="">Seçin…</option>{['D50','D65','A','F11'].map(v=><option key={v}>{v}</option>)}</select></label>
          <label className="text-xs">Gözlemci açısı<select className={style} value={color.observer} onChange={e=>setColor({...color,observer:e.target.value})}><option value="">Seçin…</option><option value="2">2°</option><option value="10">10°</option></select></label>
          <label className="text-xs">Ölçüm tarihi<input type="date" className={style} value={color.measured_at} onChange={e=>setColor({...color,measured_at:e.target.value})}/></label>
        </div>
        <p className="text-xs text-amber-300 mt-3">Mevcut fotoğraf renk motoru D65/2° kullanır. Diğer koşullar kaydedilebilir; analizde eşdeğer kabul edilmez.</p>
        <button type="button" className="mt-3 rounded-lg px-3 py-2 bg-sky-700 text-sm" onClick={addColor}>Ölçümü kartelaya ekle</button>
      </details>
    </fieldset>
    {message && <p role="status" className="text-sm whitespace-pre-wrap text-sky-200">{message}</p>}
  </section>;
}
