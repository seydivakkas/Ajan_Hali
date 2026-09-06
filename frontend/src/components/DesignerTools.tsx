import React, { useState } from 'react';
import { AnalysisPipelineResult } from '../types/carpet';
import { getDownloadUrl, resolveImageUrl } from '../services/api';

type ToolLink = {id:string; name:string; url:string; note:string};
export type DesignerDestination = 'visual' | 'colors' | 'yarn' | 'cad' | 'audit' | 'settings';
const storageKey = 'ajan-hali-designer-tools-v1';
const field = 'w-full rounded-lg p-2 bg-slate-950 border border-slate-700 text-sm';
function safeUrl(value:string) {
  try { const url=new URL(value); return ['https:','http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
function readLinks():ToolLink[] {
  try { const value=JSON.parse(localStorage.getItem(storageKey)||'[]');
    return Array.isArray(value) ? value.filter(x=>x && typeof x.id==='string' && typeof x.name==='string' && typeof x.note==='string' && typeof x.url==='string' && safeUrl(x.url)).slice(0,50) : [];
  } catch { return []; }
}
function exportCsv(name:string, rows:(string|number)[][]) {
  const csv=rows.map(row=>row.map(value=>`"${String(value).replace(/^[=+@-]/,"'$&").replace(/"/g,'""')}"`).join(';')).join('\r\n');
  const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a'); link.href=url; link.download=name; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function DesignerTools({result,onOpen}:{result:AnalysisPipelineResult|null;onOpen:(destination:DesignerDestination)=>void}) {
  const [links,setLinks]=useState<ToolLink[]>(readLinks);
  const [editing,setEditing]=useState<string|null>(null);
  const [name,setName]=useState(''); const [url,setUrl]=useState(''); const [note,setNote]=useState('');
  const [message,setMessage]=useState(''); const [repeat,setRepeat]=useState(2);
  const saveLinks=(next:ToolLink[])=>{try {localStorage.setItem(storageKey,JSON.stringify(next));setLinks(next);setMessage('Araç listesi bu tarayıcıda kaydedildi.');return true;} catch {setMessage('Tarayıcıya kaydedilemedi. Depolama iznini kontrol edin.');return false;}};
  const submit=(e:React.FormEvent)=>{e.preventDefault();const address=safeUrl(url);
    if(!address || !name.trim()){setMessage('Araç adı ve geçerli http/https adresi girin.');return;}
    if(!editing && links.length>=50){setMessage('En fazla 50 araç kaydedilebilir.');return;}
    const item={id:editing||crypto.randomUUID(),name:name.trim(),url:address,note:note.trim()};
    if(saveLinks(editing?links.map(x=>x.id===editing?item:x):[...links,item])){setEditing(null);setName('');setUrl('');setNote('');}
  };
  const native:{name:string;description:string;to:DesignerDestination;needsResult:boolean}[]=[
    {name:'Fotoğraf ve desen onarımı',description:'Fotoğraf yükleme, dört köşe seçimi, maskeleme ve simetri ayarları.',to:'visual',needsResult:false},
    {name:'Renk kontrolü',description:'İplik eşleşmelerini, renk oranlarını ve ΔE farklarını inceleyin.',to:'colors',needsResult:true},
    {name:'İplik ve ölçümlü kartela',description:'Tedarikçi, dtex, Lab, boya partisi, fiyat ve stok kayıtlarını düzenleyin.',to:'settings',needsResult:false},
    {name:'Reçete ve maliyet',description:'Renk başına tüketim, bobin sayısı ve güncel fiyatla hesaplama.',to:'yarn',needsResult:true},
    {name:'CAD dosya merkezi',description:'DXF, SVG ve matris çıktıları; deneysel CAM dosyalarının durumu.',to:'cad',needsResult:true},
    {name:'Desinatör kontrolü',description:'Kalite riskleri ve sürüme bağlı değerlendirme kaydı.',to:'audit',needsResult:true},
  ];
  return <div className="space-y-6">
    <header><h2 className="text-2xl font-semibold">Desinatör araç masası</h2><p className="text-sm text-slate-400 mt-2">Deseni hazırlayın, renkleri kontrol edin, reçeteyi inceleyin ve dosyaları kullandığınız yazılıma aktarın.</p></header>
    {result && <p className="text-sm text-sky-300">Çalışılan analiz: {result.job_id} · {result.data_source==='DEMO_SYNTHETIC'?'DEMO — üretimde kullanılmaz':'Kayıtlı analiz'}</p>}
    <section className="grid md:grid-cols-3 gap-4">{native.map(tool=><article key={tool.to} className="rounded-xl border border-slate-700 bg-slate-900 p-4 flex flex-col gap-3"><span className="text-xs text-emerald-300">Uygulama içi araç</span><h3 className="font-semibold">{tool.name}</h3><p className="text-sm text-slate-400 flex-1">{tool.description}</p><button disabled={tool.needsResult&&!result} onClick={()=>onOpen(tool.to)} className="p-2 rounded-lg bg-sky-700 disabled:opacity-40">{tool.needsResult&&!result?'Önce analiz oluşturun veya geçmişten seçin':'Aracı aç'}</button></article>)}</section>
    <section className="p-5 rounded-xl border border-slate-700 space-y-4"><h3 className="font-semibold">Dosyayla birlikte çalışın</h3><p className="text-sm text-slate-400">Dış programda dosyayı açmak için ilgili çıktıyı indirin. Bu erişim dosya aktarımıdır; programların komutlarını uzaktan çalıştırmaz.</p>
      {result ? <div className="flex flex-wrap gap-3">
        {([['dxf','DXF indir',result.dxf_export_path],['svg','SVG indir',result.svg_export_path],['report','Kaynak raporu JSON',true]] as const).filter(x=>x[2]).map(([format,label])=><a className="border border-sky-700 rounded-lg p-3 text-sm text-sky-300" key={format} href={getDownloadUrl(result.job_id,format)}>{label}</a>)}
        <button className="border border-sky-700 rounded-lg p-3 text-sm" onClick={()=>exportCsv(`${result.data_source==='DEMO_SYNTHETIC'?'DEMO_':''}${result.job_id}_palette.csv`,[['Kaynak','Kod','Renk','Malzeme','R','G','B','Alan %','Delta E ortalama'],...result.color_mappings.map(x=>[result.data_source||'BELIRSIZ',x.palette_code,x.yarn_name,x.material,...x.mapped_rgb,x.area_percentage,x.ciede2000_delta_e_avg])])}>Renk listesi CSV</button>
        <button className="border border-sky-700 rounded-lg p-3 text-sm" onClick={()=>exportCsv(`${result.data_source==='DEMO_SYNTHETIC'?'DEMO_':''}${result.job_id}_recipe.csv`,[['Kaynak','Kod','Renk','dtex','Brüt kg','Bobin','Stok kg','Eksik kg','Birim TL/kg','Toplam TL'],...result.yarn_recipe.map(x=>[result.data_source||'BELIRSIZ',x.yarn_code,x.yarn_name,x.dtex,x.total_weight_kg_gross_with_waste,x.bobbin_count_required,x.stock_available_kg,x.stock_shortage_kg,x.unit_cost_tl,x.total_cost_tl])])}>İplik reçetesi CSV</button>
      </div>:<p className="text-sm text-amber-300">Dosya araçları için bir analiz açın.</p>}
    </section>
    {result && <section className="p-5 rounded-xl border border-slate-700 space-y-3"><h3 className="font-semibold">Raport birleşim önizlemesi</h3><p className="text-sm text-slate-400">Mevcut desenin kenar birleşimlerini tekrar ederek inceleyin. Bu görünüm deseni veya üretim matrisini değiştirmez.</p><label className="text-sm">Tekrar sayısı <select className={field} value={repeat} onChange={e=>setRepeat(Number(e.target.value))}>{[2,3,4].map(n=><option key={n} value={n}>{n} × {n}</option>)}</select></label><div className="grid max-w-2xl border border-slate-700" style={{gridTemplateColumns:`repeat(${repeat},minmax(0,1fr))`}}>{Array.from({length:repeat*repeat},(_,i)=><img key={`${result.job_id}-${i}`} src={resolveImageUrl(result.quantized_preview_path)} alt={i===0?'Desenin tekrarlı raport önizlemesi':''} className="w-full block"/>)}</div></section>}
    <section className="p-5 rounded-xl border border-slate-700 space-y-4"><h3 className="font-semibold">Firmanın yazılım ve sistemleri</h3><p className="text-sm text-slate-400">Web tabanlı çizim, ERP, dosya arşivi veya tedarikçi portalını ekleyin. Bağlantılar yalnızca bu tarayıcıda tutulur; giriş bilgisi eklemeyin. Masaüstü yazılımlarını kendi bilgisayarınızda açıp yukarıdaki dosyaları içe aktarın.</p>
      {!links.length&&<p className="text-sm text-amber-300">Henüz dış yazılım tanımlanmadı. Bağlantı eklemek API entegrasyonu veya lisans sağlamaz.</p>}
      <div className="grid md:grid-cols-2 gap-3">{links.map(link=><article key={link.id} className="bg-slate-900 border border-slate-700 p-4 rounded-lg space-y-2"><h4 className="font-semibold">{link.name}</h4><p className="text-xs text-slate-400 break-all">{link.url}</p><p className="text-sm">{link.note}</p><div className="flex gap-4 text-sm"><a className="text-sky-300" href={safeUrl(link.url)||undefined} target="_blank" rel="noopener noreferrer">Web aracını aç ↗</a><button onClick={()=>{setEditing(link.id);setName(link.name);setUrl(link.url);setNote(link.note);}}>Düzenle</button><button className="text-rose-300" onClick={()=>{if(saveLinks(links.filter(x=>x.id!==link.id))&&editing===link.id){setEditing(null);setName('');setUrl('');setNote('');}}}>Sil</button></div></article>)}</div>
      <form onSubmit={submit} className="grid md:grid-cols-3 gap-3"><label className="text-xs">Yazılım / sistem adı<input required maxLength={100} className={field} value={name} onChange={e=>setName(e.target.value)}/></label><label className="text-xs">Web adresi<input required type="url" maxLength={2000} className={field} value={url} onChange={e=>setUrl(e.target.value)}/></label><label className="text-xs">Kullanım notu<input maxLength={500} className={field} value={note} onChange={e=>setNote(e.target.value)}/></label><button className="p-2 rounded-lg bg-sky-700">{editing?'Aracı güncelle':'Web aracı ekle'}</button>{editing&&<button type="button" onClick={()=>{setEditing(null);setName('');setUrl('');setNote('');}}>Düzenlemeyi iptal et</button>}</form>
      {message&&<p role="status" className="text-sm text-sky-300">{message}</p>}
    </section>
  </div>;
}
