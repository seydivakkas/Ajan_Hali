import React, { useEffect, useState } from 'react';
import { uploadSpectroFile } from '../services/api';
import { FactorySettings, FactoryYarn, putSettings, changeDemoInventory } from '../services/settings';
import { SupplierCatalog, fetchCatalog } from '../services/catalog';
import { SupplierCatalogPanel } from './SupplierCatalogPanel';
const inputStyle = 'w-full mt-1 rounded-lg bg-slate-950 border border-slate-700 p-2 text-sm focus:border-sky-400';
const blankYarn = (): FactoryYarn => ({ code:'', name:'', material:'', dtex:null, rgb:[0,0,0], lab:[null,null,null], color_source:'MEASURED_LAB', cost_per_kg_tl:null, bobbin_weight_kg:null, stock_kg:null });
const colorOptions = ['Krem Ekru', 'Kemik Bej', 'Vizon Gri', 'Antrasit', 'Koyu Lacivert', 'Bordo', 'Kiremit', 'Zümrüt', 'Safran', 'Gül Kurusu', 'Açık Gri', 'Kahverengi'];
const materialOptions = ['PP Heatset BCF', 'PP Frize', 'Polyester', 'Viskon', 'Bambu İpek', 'Yün', 'Akrilik'];

function ChoiceField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const isOption = value !== '' && options.includes(value);
  const [custom, setCustom] = useState(value !== '' && !isOption);
  return <div className="text-xs">
    <span>{label}</span>
    <select
      aria-label={label}
      required={!custom}
      className={inputStyle}
      value={custom ? '__custom__' : value}
      onChange={event => {
        const next = event.target.value;
        if (next === '__custom__') {
          setCustom(true);
          onChange('');
        } else {
          setCustom(false);
          onChange(next);
        }
      }}
    >
      <option value="">Seçin…</option>
      {options.map(option => <option key={option} value={option}>{option}</option>)}
      <option value="__custom__">Özel değer…</option>
    </select>
    {custom && <input
      aria-label={`${label} özel değer`}
      autoFocus
      required
      className={inputStyle}
      placeholder={`${label} yazın`}
      value={value}
      onChange={event => onChange(event.target.value)}
    />}
  </div>;
}
export function FactorySettingsPanel({ initial, onSaved }: { initial: FactorySettings; onSaved: (s: FactorySettings) => void }) {
  const [draft, setDraft] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [catalog, setCatalog] = useState<SupplierCatalog>({products:[], colors:[]});
  const [catalogError, setCatalogError] = useState('');
  const reloadCatalog = () => { setCatalogError(''); fetchCatalog().then(setCatalog).catch(e=>setCatalogError(e.message)); };
  useEffect(reloadCatalog, []);
  const edit = (s: FactorySettings) => { setDraft(s); setDirty(true); setMessage(''); };
  const demoAction = async (remove = false) => {
    setBusy(true); setMessage('');
    try {
      const next = await changeDemoInventory(draft.revision, remove);
      setDraft(next); onSaved(next); setDirty(false);
      setMessage(remove ? 'Demo iplikler silindi. Şirket kayıtları korundu. Demo analizlerini Analiz geçmişi bölümünden ayrıca silebilirsiniz.' : '4 sentetik demo iplik kaydedildi. Fiyat ve stokları değiştirerek hesaplamayı deneyebilirsiniz.');
    } catch(e: any) { setMessage(e.message); } finally { setBusy(false); }
  };
  const yarn = (index: number, update: Partial<FactoryYarn>) => edit({ ...draft, yarns: draft.yarns.map((y,i) => i === index ? { ...y, ...update } : y) });
  const importMeasurements = async (file: File) => {
    setBusy(true); setMessage('');
    try {
      const result = await uploadSpectroFile(file);
      edit({ ...draft, yarns: [...draft.yarns, ...result.samples.map((s: any) => ({...blankYarn(),name:s.name,lab:s.lab}))] });
      setMessage(`${result.samples.length} ölçüm taslağa eklendi. Kod, malzeme, dtex, fiyat, stok ve bobin ağırlığını tamamlayıp kaydedin. Ölçüm koşullarını cihaz kaydınızla kontrol edin.`);
    } catch(e: any) { setMessage(e.message); } finally { setBusy(false); }
  };
  const save = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setMessage('');
    try { const result = await putSettings(draft); setDraft(result); setDirty(false); onSaved(result); setMessage('Fabrika bilgileri kaydedildi. Yeni analizler bu değerleri kullanır.'); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  };
  return <form onSubmit={save} className="space-y-6">
    <div className="flex flex-wrap justify-between gap-4 items-start">
      <div><h2 className="text-xl font-semibold">Fabrika ayarları</h2><p className="text-sm text-slate-400 mt-2">İplik, fiyat, stok ve tezgâh bilgilerini şirket kayıtlarınızdan girin. Boş alanlar otomatik doldurulmaz.</p></div>
      <button disabled={busy || !dirty} className="px-5 py-3 bg-sky-500 rounded-lg text-slate-950 font-semibold disabled:opacity-40">{busy ? 'Kaydediliyor…' : dirty ? 'Değişiklikleri kaydet' : draft.revision ? 'Kaydedildi' : 'Bilgileri girin'}</button>
    </div>
    <p className="text-xs text-slate-400">Veri kaynağı: kullanıcı girişi · Revizyon {draft.revision} · {draft.updated_at ? new Date(draft.updated_at).toLocaleString('tr-TR') : 'Henüz şirket verisi yok'} {dirty && '· Kaydedilmemiş değişiklikler'}</p>
    {message && <p role="status" className="whitespace-pre-wrap p-4 rounded-lg border border-sky-600 text-sm">{message}</p>}
    <fieldset disabled={busy} className="space-y-6">
      <section className="p-4 rounded-xl border border-amber-700 bg-amber-950/20 space-y-3">
        <h3 className="font-semibold text-amber-300">Eğitim ve test · DEMO</h3>
        <p className="text-sm text-slate-300">4 örnek iplik: 1800 dtex, 5 kg bobin ve sentetik Lab / fiyat / stok değerleri. Bordo stok miktarı eksik stok senaryosunu denemek için düşüktür. Gerçek tedarikçi ölçümü değildir; katalog kayıtlarını değiştirmez.</p>
        <ol className="list-decimal pl-5 text-xs text-slate-400 space-y-1"><li>Demo iplikleri yükleyin; envanterde fiyat, stok ve bobin alanlarını inceleyin.</li><li>Analiz stüdyosunda örnek parametreleri doldurun ve bir halı fotoğrafı yükleyin.</li><li>Renk eşlemesi, reçete, maliyet ve kalite uyarılarını karşılaştırın. Sonuç üretim için kullanılmaz.</li><li>Demo iplikleri ve analiz geçmişindeki demo sonuçlarını silin.</li></ol>
        <div className="flex flex-wrap gap-3">
          <button type="button" disabled={dirty || draft.yarns.some(y=>y.is_demo)} onClick={()=>demoAction()} className="px-3 py-2 rounded-lg bg-amber-700 disabled:opacity-40">Demo iplikleri yükle</button>
          <button type="button" disabled={dirty || !draft.yarns.some(y=>y.is_demo)} onClick={()=>demoAction(true)} className="px-3 py-2 rounded-lg border border-rose-700 text-rose-300 disabled:opacity-40">Demo iplikleri sil</button>
        </div>
        {dirty && <p className="text-xs text-amber-300">Demo işlemlerinden önce düzenlemelerinizi kaydedin.</p>}
      </section>
      <section className="grid md:grid-cols-3 gap-4 p-4 border border-slate-800 rounded-xl bg-slate-900">
        <label className="text-xs">Şirket adı<input required={!draft.yarns.some(y=>y.is_demo)} maxLength={150} className={inputStyle} value={draft.company_name} onChange={e => edit({...draft, company_name:e.target.value})} /></label>
        <label className="text-xs">ERP sistemi (isteğe bağlı)<input maxLength={100} className={inputStyle} value={draft.erp_system} onChange={e => edit({...draft, erp_system:e.target.value})} /></label>
        <label className="text-xs">Attio şirket kayıt ID (isteğe bağlı)<input maxLength={100} className={inputStyle} value={draft.attio_company_record_id} onChange={e => edit({...draft, attio_company_record_id:e.target.value})} /></label>
        <p className="text-xs text-slate-400 md:col-span-3">ERP ve Attio alanları bağlantı referansıdır. Bu ekran dış sistemlere veri göndermez.</p>
      </section>
      {catalogError && <p role="alert" className="text-xs text-rose-300">Katalog yüklenemedi: {catalogError} <button type="button" className="underline" onClick={reloadCatalog}>Yeniden dene</button></p>}
      <SupplierCatalogPanel catalog={catalog} onChange={setCatalog} />
      <section className="space-y-4">
        <div className="flex items-center justify-between"><h3 className="font-semibold">İplik envanteri · {draft.yarns.length} renk</h3><button type="button" className="text-sky-300 border border-sky-800 px-3 py-2 rounded-lg" onClick={() => edit({...draft, yarns:[...draft.yarns,blankYarn()]})}>+ İplik ekle</button></div>
        <label className="block text-xs text-slate-400">Ölçüm dosyasından Lab ekle (QTX / CXF; fiyat ve stok eklenmez)
          <input type="file" accept=".qtx,.cxf,.xml" className="block mt-2 text-xs" onChange={e => { const file=e.target.files?.[0]; if(file) void importMeasurements(file); e.target.value=''; }} />
        </label>
        {draft.yarns.length === 0 && <p className="p-8 text-center border border-dashed border-slate-700 rounded-xl text-slate-400">Henüz iplik tanımlanmadı. Analiz için gerçek fabrika paletinizi oluşturun.</p>}
        {draft.yarns.map((y,i) => <article key={i} className="p-4 rounded-xl border border-slate-700 bg-slate-900 space-y-4">
          {y.is_demo && <p className="text-xs text-amber-300">DEMO — Sentetik eğitim verisi. Düzenlense de demo etiketi korunur.</p>}
          <div className="flex justify-between"><strong className="text-sm">{y.code || `İplik ${i+1}`}</strong><button type="button" className="text-xs text-rose-300" onClick={() => edit({...draft,yarns:draft.yarns.filter((_,index) => index !== i)})}>Satırı kaldır</button></div>
          <div className="grid sm:grid-cols-2 gap-3 rounded-lg border border-sky-900 p-3">
            <label className="text-xs">Tedarikçi kataloğundan iplik seç
              <select className={inputStyle} value={y.catalog_product_id || ''} onChange={e=>{
                const product = catalog.products.find(p=>p.id===e.target.value);
                yarn(i, product ? {catalog_product_id:product.id, catalog_color_id:null, catalog_snapshot:{product,color:null}, material:product.material, dtex:product.dtex, name:'', lab:[null,null,null], cost_per_kg_tl:null, stock_kg:null, bobbin_weight_kg:null}
                  : {catalog_product_id:null,catalog_color_id:null,catalog_snapshot:null});
              }}>
                <option value="">Manuel giriş</option>
                {catalog.products.map(p=><option key={p.id} value={p.id}>{p.supplier} · {p.product_code} · {p.dtex} dtex</option>)}
              </select>
            </label>
            <label className="text-xs">Bu ipliğin ölçümlü kartelası
              <select className={inputStyle} disabled={!y.catalog_product_id} value={y.catalog_color_id || ''} onChange={e=>{
                const color=catalog.colors.find(c=>c.id===e.target.value);
                const product=catalog.products.find(p=>p.id===y.catalog_product_id);
                yarn(i,color && product ? {catalog_color_id:color.id,catalog_snapshot:{product,color},name:color.name,lab:color.lab,color_source:'MEASURED_LAB'}
                  : {catalog_color_id:null,catalog_snapshot:product?{product,color:null}:null});
              }}>
                <option value="">Manuel Lab girişi</option>
                {catalog.colors.filter(c=>c.product_id===y.catalog_product_id).map(c=><option key={c.id} value={c.id}>{c.color_code} · {c.name} · Parti {c.dye_lot} · {c.illuminant}/{c.observer}°</option>)}
              </select>
            </label>
            {!catalog.products.length && <p className="text-xs text-slate-400 sm:col-span-2">Katalog boş. Yukarıdan gerçek tedarikçi kaydı ekleyin veya JSON kataloğunuzu yükleyin.</p>}
            {!!y.catalog_product_id && !catalog.colors.some(c=>c.product_id===y.catalog_product_id) && <p className="text-xs text-amber-300 sm:col-span-2">Bu ipliğe bağlı ölçümlü renk henüz yok. Kartela kaydı ekleyin veya Lab değerlerini elle girin.</p>}
          </div>
          {y.catalog_snapshot && <div className="text-xs text-slate-400 space-y-1 break-words">
            <p>dtex / malzeme kaynağı: {y.catalog_snapshot.product.supplier} · {y.catalog_snapshot.product.product_code} · {y.catalog_snapshot.product.count_value} {y.catalog_snapshot.product.count_unit} → {y.catalog_snapshot.product.dtex} dtex</p>
            <p>Belge: {y.catalog_snapshot.product.source_ref}</p>
            {y.catalog_snapshot.color && <>
              <p>Renk kaynağı: {y.catalog_snapshot.color.color_code} · Parti {y.catalog_snapshot.color.dye_lot} · {y.catalog_snapshot.color.illuminant}/{y.catalog_snapshot.color.observer}° · {y.catalog_snapshot.color.device} · {y.catalog_snapshot.color.measured_at}</p>
              <p>Ölçüm raporu: {y.catalog_snapshot.color.source_ref}</p>
              {(y.catalog_snapshot.color.illuminant!=='D65' || y.catalog_snapshot.color.observer!=='2') && <p className="text-amber-300">Bu ölçüm koşulu mevcut D65/2° analiz motoruyla uyumlu değil. Kayıt saklanır; analiz için aynı koşulda ölçüm gerekir.</p>}
            </>}
            <p>Kaynaktan doldurulan alanları düzenlemek için ilgili seçimden “Manuel giriş” seçin. Fiyat ve stok şirket girişidir.</p>
          </div>}
          <div className="grid sm:grid-cols-3 gap-3">
            <label className="text-xs">Stok kodu<input required className={inputStyle} value={y.code} onChange={e => yarn(i,{code:e.target.value})} /></label>
            {y.catalog_color_id ? <label className="text-xs">Renk adı (karteladan)<input readOnly className={inputStyle} value={y.name}/></label> : <ChoiceField label="Renk adı" value={y.name} options={[...new Set([...colorOptions, ...draft.yarns.map(item => item.name).filter(Boolean)])]} onChange={value => yarn(i, { name: value })} />}
            {y.catalog_product_id ? <label className="text-xs">Malzeme (katalogdan)<input readOnly className={inputStyle} value={y.material}/></label> : <ChoiceField label="Malzeme" value={y.material} options={[...new Set([...materialOptions, ...draft.yarns.map(item => item.material).filter(Boolean)])]} onChange={value => yarn(i, { material: value })} />}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {(['dtex','cost_per_kg_tl','bobbin_weight_kg','stock_kg'] as const).map((key,index) => <label key={key} className="text-xs">{['İplik numarası (dtex)','Birim fiyat (TL/kg)','Net bobin ağırlığı (kg)','Kullanılabilir stok (kg)'][index]}<input required readOnly={key==='dtex' && !!y.catalog_product_id} type="number" min={key === 'dtex' ? .000001 : key === 'bobbin_weight_kg' ? .001 : 0} step="any" className={inputStyle} value={y[key] ?? ''} onChange={e => yarn(i,{[key]:e.target.value === '' ? null : Number(e.target.value)})} /></label>)}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="text-xs">Ekran önizlemesi<div className="h-10 mt-1 rounded border border-slate-700" style={{ backgroundColor: `rgb(${y.rgb.join(',')})` }} /><span className="text-slate-500">Kayıtta Lab'dan hesaplanır</span></div>
            {['L* (0–100)','a*','b*'].map((label,index) => <label key={label} className="text-xs">{label}<input required readOnly={!!y.catalog_color_id} type="number" min={index === 0 ? 0 : -160} max={index === 0 ? 100 : 160} step="any" className={inputStyle} value={y.lab[index] ?? ''} onChange={e => yarn(i,{lab:y.lab.map((v,j) => j === index ? e.target.value === '' ? null : Number(e.target.value) : v) as FactoryYarn['lab']})} /></label>)}
          </div>
          <p className="text-xs text-slate-400">Lab değerlerini ölçüm kaydınızdan girin. Ekran rengi yalnızca görsel önizlemedir; renk eşlemesinde Lab kullanılır.</p>
        </article>)}
      </section>
      <section className="space-y-4">
        <div className="flex justify-between"><h3 className="font-semibold">Tezgâh bağlantı bilgileri</h3><button type="button" className="text-sky-300" onClick={() => edit({...draft,looms:[...draft.looms,{name:'',controller_model:'',ip:null,port:null,protocol:null}]})}>+ Tezgâh ekle</button></div>
        {draft.looms.length === 0 && <p className="text-sm text-slate-400">Tezgâh tanımlanmadı. IP veya kontrolör bilgisi varsayılmıyor.</p>}
        {draft.looms.map((loom,i) => <div key={i} className="grid md:grid-cols-3 gap-3 bg-slate-900 border border-slate-700 p-4 rounded-xl">
          {(['name','controller_model','ip'] as const).map((key,index) => <label key={key} className="text-xs">{['Tezgâh adı','Kontrolör modeli','IP adresi (isteğe bağlı)'][index]}<input required={key !== 'ip'} className={inputStyle} value={loom[key] || ''} onChange={e => edit({...draft,looms:draft.looms.map((l,j) => j===i ? {...l,[key]:e.target.value || (key==='ip' ? null : '')} : l)})} /></label>)}
          <label className="text-xs">Port<input type="number" min={1} max={65535} className={inputStyle} value={loom.port ?? ''} onChange={e => edit({...draft,looms:draft.looms.map((l,j) => j===i ? {...l,port:e.target.value ? Number(e.target.value) : null} : l)})} /></label>
          <label className="text-xs">Aktarım protokolü<select className={inputStyle} value={loom.protocol || ''} onChange={e => edit({...draft,looms:draft.looms.map((l,j) => j===i ? {...l,protocol:(e.target.value || null) as typeof loom.protocol} : l)})}><option value="">Belirtilmedi</option><option>FTP</option><option>SFTP</option><option>SMB</option></select></label>
          <button type="button" className="text-xs text-rose-300" onClick={() => edit({...draft,looms:draft.looms.filter((_,j)=>j!==i)})}>Tezgâhı kaldır</button>
        </div>)}
        <p className="text-xs text-amber-300">IP kaydetmek bağlantı kurmaz. Kontrolör adaptörü doğrulanana kadar doğrudan gönderim kapalıdır.</p>
      </section>
    </fieldset>
  </form>;
}
