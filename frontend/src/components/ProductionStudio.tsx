import React,{useEffect,useMemo,useRef,useState} from 'react';
import { YarnRecipeTable } from './YarnRecipeTable';
import {composeStudio,downloadStudio,fetchRevision,fetchStudio,saveRevision,StudioDocument,StudioLayer,StudioState} from '../services/studio';

const input='bg-slate-950 border border-slate-700 rounded p-2 w-full text-sm';
const button='px-3 py-2 rounded border border-slate-700 text-sm disabled:opacity-40 hover:bg-slate-800';
type Rect={x:number;y:number;width:number;height:number};
type History={past:StudioDocument[];present:StudioDocument;future:StudioDocument[]};

export function ProductionStudio({jobId,onDirty}:{jobId:string|null;onDirty:(dirty:boolean)=>void}){
  const currentJob=useRef(jobId);currentJob.current=jobId;
  const [state,setState]=useState<StudioState|null>(null);const [history,setHistory]=useState<History|null>(null);
  const [active,setActive]=useState('base');const [color,setColor]=useState(0);const [zoom,setZoom]=useState(2);
  const [tool,setTool]=useState<'paint'|'erase'|'select'>('paint');const [selection,setSelection]=useState<Rect|null>(null);
  const [start,setStart]=useState<{x:number;y:number}|null>(null);const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');const [dirty,setDirty]=useState(false);const [author,setAuthor]=useState('');const [note,setNote]=useState('');
  const [selectedRevision,setSelectedRevision]=useState('');const canvas=useRef<HTMLCanvasElement>(null);
  const doc=history?.present;const layer=doc?.layers.find(l=>l.id===active)||doc?.layers[0];
  const composite=useMemo(()=>doc?composeStudio(doc):[],[doc]);
  const markDirty=(value:boolean)=>{setDirty(value);onDirty(value);};
  useEffect(()=>{let cancelled=false;setState(null);setHistory(null);setError('');setSelection(null);setStart(null);setSelectedRevision('');markDirty(false);
    if(!jobId){setBusy(false);return;}setBusy(true);fetchStudio(jobId).then(s=>{if(!cancelled){setState(s);setHistory({past:[],present:s.document,future:[]});setActive(s.document.layers[0].id);}}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setBusy(false);});return()=>{cancelled=true;};
  },[jobId]);
  useEffect(()=>{if(!dirty)return;const handler=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[dirty]);
  useEffect(()=>{if(!doc||!state||!canvas.current)return;const ctx=canvas.current.getContext('2d');if(!ctx)return;
    const image=ctx.createImageData(doc.width,doc.height);for(let i=0;i<composite.length;i++){const rgb=state.palette[composite[i]]?.rgb||[255,0,255];image.data.set([...rgb,255],i*4);}ctx.putImageData(image,0,0);
    if(selection){ctx.strokeStyle='#00ffff';ctx.lineWidth=1;ctx.strokeRect(selection.x+.5,selection.y+.5,selection.width-1,selection.height-1);}
  },[doc,state,composite,selection]);
  const commit=(next:StudioDocument)=>{if(!doc)return;const limit=Math.max(1,Math.min(30,Math.floor(8_000_000/doc.layers.reduce((n,l)=>n+l.cells.length,0))));setHistory(h=>h?{past:[...h.past,h.present].slice(-limit),present:next,future:[]}:h);markDirty(true);setError('');};
  const changeLayer=(change:Partial<StudioLayer>)=>{if(!doc||!layer)return;commit({...doc,layers:doc.layers.map(l=>l.id===layer.id?{...l,...change}:l)});};
  const undo=(redo=false)=>{if(!history)return;const from=redo?history.future:history.past;if(!from.length)return;const next=from[from.length-1];setHistory(redo?{past:[...history.past,history.present],present:next,future:from.slice(0,-1)}:{past:from.slice(0,-1),present:next,future:[...history.future,history.present]});markDirty(true);};
  const click=(event:React.MouseEvent<HTMLCanvasElement>)=>{if(!doc||!layer||busy)return;const bounds=event.currentTarget.getBoundingClientRect();const x=Math.min(doc.width-1,Math.max(0,Math.floor((event.clientX-bounds.left)*doc.width/bounds.width)));const y=Math.min(doc.height-1,Math.max(0,Math.floor((event.clientY-bounds.top)*doc.height/bounds.height)));
    if(tool==='select'){if(!start){setStart({x,y});setSelection({x,y,width:1,height:1});}else{setSelection({x:Math.min(x,start.x),y:Math.min(y,start.y),width:Math.abs(x-start.x)+1,height:Math.abs(y-start.y)+1});setStart(null);}return;}
    if(!layer.visible){setError('Boyamak için katmanı görünür yapın.');return;}
    if(x<layer.x||y<layer.y||x>=layer.x+layer.width||y>=layer.y+layer.height){setError('Hücre seçili katmanın dışında.');return;}
    if(tool==='erase'&&layer.role==='BASE'){setError('Taban şeffaf bırakılamaz; bir iplik rengiyle boyayın.');return;}
    const cells=[...layer.cells];cells[(y-layer.y)*layer.width+x-layer.x]=tool==='erase'?-1:color;changeLayer({cells});
  };
  const motif=()=>{if(!doc||!selection)return;if(doc.layers.length>=16){setError('En fazla 16 katman.');return;}const raw=composeStudio(doc,false);const cells=[];for(let y=0;y<selection.height;y++)for(let x=0;x<selection.width;x++)cells.push(raw[(selection.y+y)*doc.width+selection.x+x]);const newLayer:StudioLayer={id:crypto.randomUUID(),name:`Motif ${doc.layers.length}`,role:'MOTIF',visible:true,...selection,cells};commit({...doc,layers:[...doc.layers,newLayer]});setActive(newLayer.id);};
  const transform=(axis:'horizontal'|'vertical')=>{if(!layer)return;const cells=layer.cells.map((_,i)=>{const x=i%layer.width,y=Math.floor(i/layer.width);return layer.cells[(axis==='vertical'?layer.height-1-y:y)*layer.width+(axis==='horizontal'?layer.width-1-x:x)];});changeLayer({cells});};
  const tile=()=>{if(!doc||!selection)return;const raw=composeStudio(doc,false);const cells=raw.map((_,i)=>raw[(selection.y+Math.floor(i/doc.width)%selection.height)*doc.width+selection.x+(i%doc.width)%selection.width]);commit({...doc,layers:[{id:'base',name:'Raport tabanı',role:'BASE',visible:true,x:0,y:0,width:doc.width,height:doc.height,cells}]});setActive('base');};
  const save=async(kind:string)=>{
    if(!state||!doc)return;
    if(author.trim().length<2||note.trim().length<3){setError('Desinatör adı ve en az 3 karakterlik revizyon notu girin.');return;}
    const savingJob=state.job_id;
    setBusy(true);setError('');
    try{
      const saved=await saveRevision(savingJob,state.revision,doc,author,note,kind);
      if(currentJob.current!==savingJob)return;
      setState({...state,revision:saved.revision,document:doc,evaluation:saved.evaluation,history:[{
        revision:saved.revision,parent_revision:saved.parent_revision,author:saved.author,note:saved.note,
        kind:saved.kind,created_at:saved.created_at,sha256:saved.sha256},...state.history]});
      markDirty(false);setNote('');setSelectedRevision(String(saved.revision));
    }catch(e:any){if(currentJob.current===savingJob)setError(e.message);}
    finally{if(currentJob.current===savingJob)setBusy(false);}
  };
  const openRevision=async()=>{
    if(!state||!selectedRevision)return;
    if(dirty&&!window.confirm('Kaydedilmemiş değişiklikler yerine seçilen revizyon açılsın mı?'))return;
    const openingJob=state.job_id;setBusy(true);
    try{
      const old=await fetchRevision(openingJob,Number(selectedRevision));
      if(currentJob.current!==openingJob)return;
      commit(old.document);setActive(old.document.layers[0].id);setSelection(null);setStart(null);
    }catch(e:any){if(currentJob.current===openingJob)setError(e.message);}
    finally{if(currentJob.current===openingJob)setBusy(false);}
  };
  const downloadSaved=async()=>{
    if(!state||!selectedRevision)return;
    const downloadingJob=state.job_id;setBusy(true);
    try{
      const value=await fetchRevision(downloadingJob,Number(selectedRevision));
      if(currentJob.current!==downloadingJob)return;
      downloadStudio(`${value.data_source==='DEMO_SYNTHETIC'?'DEMO_':''}${downloadingJob}_studio_r${selectedRevision}.json`,value);
    }catch(e:any){if(currentJob.current===downloadingJob)setError(e.message);}
    finally{if(currentJob.current===downloadingJob)setBusy(false);}
  };
  if(!jobId)return <section className="p-8 rounded-xl border border-slate-700"><h2 className="text-xl">Desen Studio · V1.1</h2><p className="mt-3 text-slate-400">Yeni analiz oluşturun veya Analiz stüdyosunun geçmişinden bir analiz seçin. Studio gerçek düğüm matrisini açar.</p></section>;
  return <section className="space-y-4">
    <header><h2 className="text-2xl font-semibold">Desen Studio · V1.1</h2><p className="text-sm text-slate-400 mt-2">{jobId} · {state?.data_source==='DEMO_SYNTHETIC'?'DEMO · ':''}Revizyon {state?.revision||0} · {dirty?'Kaydedilmemiş taslak':'Kayıtlı durum'}</p><p className="text-xs text-amber-300 mt-2">Studio düzenlemeleri kaynak analizden ayrıdır. Eski reçete, ΔE ve CAD dosyaları bu taslağın çıktısı değildir. Master adayı üretim onayı sağlamaz.</p></header>
    {error&&<p role="alert" className="p-3 border border-rose-700 text-rose-300 rounded">{error}</p>}{busy&&<p role="status">İşleniyor…</p>}
    {doc&&state&&layer&&<fieldset disabled={busy} className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center"><button className={button} disabled={!history?.past.length} onClick={()=>undo()}>Geri al</button><button className={button} disabled={!history?.future.length} onClick={()=>undo(true)}>Yinele</button><label className="text-xs">Araç <select className={input} value={tool} onChange={e=>{setTool(e.target.value as typeof tool);setStart(null);}}><option value="paint">Düğüm boya · tek hücre</option><option value="erase">Katmanda şeffaf sil</option><option value="select">Motif seç · iki köşe tıkla</option></select></label><label className="text-xs">Yakınlaştırma<select className={input} value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[.5,1,2,4,8,16].map(z=><option key={z} value={z}>{z*100}%</option>)}</select></label><span className="text-xs text-slate-400">{doc.width} çözgü × {doc.height} atkı · Her hücre bir iplik indeksi</span></div>
      <div className="grid xl:grid-cols-[260px_1fr_280px] gap-4">
        <aside className="space-y-3 border border-slate-700 p-3 rounded-xl"><h3 className="font-semibold">Katman / motif</h3><p className="text-xs text-slate-400">Liste üstten alta çizilir; son katman en üsttedir.</p>{doc.layers.map((l,i)=><button key={l.id} className={`${button} w-full text-left ${l.id===layer.id?'bg-sky-900':''}`} onClick={()=>setActive(l.id)}>{i+1}. {l.name} · {l.visible?'Görünür':'Gizli'}</button>)}
          <label className="block text-xs">Katman adı<input className={input} maxLength={100} value={layer.name} onChange={e=>changeLayer({name:e.target.value})}/></label>
          {layer.role!=='BASE'&&<><label className="block text-xs">Bölüm<select className={input} value={layer.role} onChange={e=>changeLayer({role:e.target.value as StudioLayer['role']})}><option value="MOTIF">Motif</option><option value="BORDER">Bordür</option><option value="FIELD">Zemin</option><option value="MEDALLION">Madalyon</option></select></label><label className="text-xs"><input type="checkbox" checked={layer.visible} onChange={e=>changeLayer({visible:e.target.checked})}/> Görünür</label><div className="grid grid-cols-2 gap-2">{(['x','y'] as const).map(k=><label className="text-xs" key={k}>{k==='x'?'Çözgü X':'Atkı Y'}<input className={input} type="number" min={0} max={k==='x'?doc.width-layer.width:doc.height-layer.height} value={layer[k]} onChange={e=>{const n=Number(e.target.value);if(Number.isInteger(n)&&n>=0&&n<=(k==='x'?doc.width-layer.width:doc.height-layer.height))changeLayer({[k]:n});}}/></label>)}</div><button className={button} onClick={()=>{commit({...doc,layers:doc.layers.filter(l=>l.id!==layer.id)});setActive('base');}}>Katmanı sil</button><button className={button} onClick={()=>commit({...doc,layers:[...doc.layers.filter(l=>l.id!==layer.id),layer]})}>En üste taşı</button></>}
          <button className={button} onClick={()=>transform('horizontal')}>Yatay ayna</button><button className={button} onClick={()=>transform('vertical')}>Dikey ayna</button>
          <h4 className="text-sm">Seçim ve raport</h4><p className="text-xs text-slate-400">{selection?`X ${selection.x}, Y ${selection.y} · ${selection.width} × ${selection.height}`:'Seçim aracıyla iki köşe belirleyin.'}{start?' · İkinci köşeyi seçin.':''}</p><button className={button} disabled={!selection||!!start} onClick={motif}>Seçimi motif katmanına kopyala</button><button className={button} disabled={!selection||!!start} onClick={tile}>Seçimi tüm matriste tekrarla</button><p className="text-xs text-amber-300">Raport uygulaması katmanları tek tabana indirger; geri alınabilir. Bordür/zemin/madalyon ayrımı manueldir.</p>
        </aside>
        <div className="border border-slate-700 rounded-xl overflow-auto max-h-[75vh] bg-slate-900 p-2"><canvas ref={canvas} width={doc.width} height={doc.height} onClick={click} aria-label="Düğüm matrisi düzenleme alanı" style={{width:doc.width*zoom,height:doc.height*zoom,imageRendering:'pixelated',maxWidth:'none',cursor:tool==='select'?'crosshair':'cell'}}/></div>
        <aside className="space-y-3 border border-slate-700 p-3 rounded-xl"><h3 className="font-semibold">Colorway Studio</h3><label className="text-xs block">Boyama ipliği<select className={input} value={color} onChange={e=>setColor(Number(e.target.value))}>{state.palette.map((p,i)=><option key={p.code} value={i}>{p.code} · {p.name}</option>)}</select></label><p className="text-xs text-slate-400">Colorway eşlemesi bütün görünür katmanlara uygulanır. Yeni iplik yalnızca kaynak paletten seçilir.</p>{state.palette.map((p,i)=><label key={p.code} className="block text-xs"><span className="inline-block w-3 h-3 mr-2" style={{backgroundColor:`rgb(${p.rgb.join(',')})`}}/>{p.code} →<select className={input} value={doc.colorway[i]} onChange={e=>commit({...doc,colorway:doc.colorway.map((c,j)=>j===i?Number(e.target.value):c)})}>{state.palette.map((target,j)=><option key={target.code} value={j}>{target.code} · {target.name}</option>)}</select></label>)}<button className={button} onClick={()=>commit({...doc,colorway:state.palette.map((_,i)=>i)})}>Colorway eşlemesini sıfırla</button></aside>
      </div>
      <section className="p-4 rounded-xl border border-slate-700 space-y-3"><h3 className="font-semibold">Revizyon ve Production Master adayı</h3><div className="grid md:grid-cols-2 gap-3"><label className="text-xs">Desinatör adı<input className={input} value={author} maxLength={100} onChange={e=>setAuthor(e.target.value)}/></label><label className="text-xs">Değişiklik notu<input className={input} value={note} maxLength={1000} onChange={e=>setNote(e.target.value)}/></label></div><div className="flex flex-wrap gap-2"><button className={button} onClick={()=>save('DRAFT')}>Taslak revizyonu kaydet</button><button className={button} onClick={()=>save('MASTER_CANDIDATE')}>Master adayı oluştur ve reçeteyi hesapla</button><button className={button} onClick={()=>downloadStudio(`${state.data_source==='DEMO_SYNTHETIC'?'DEMO_':''}${jobId}_UNSAVED_DRAFT.json`,{job_id:jobId,parent_revision:state.revision,data_source:state.data_source,document:doc,production_approved:false})}>Açık taslağı JSON indir</button></div><p className="text-xs text-slate-400">Kayıtlar kalıcı ve değiştirilemez. Eski revizyonu açmak yeni bir taslak oluşturur; kaydetmek yeni revizyon ekler. Desinatör adı kullanıcı beyanıdır, kimlik doğrulaması değildir.</p>
      <div className="flex flex-wrap gap-2"><label className="text-xs flex-1">Geçmiş<select className={input} value={selectedRevision} onChange={e=>setSelectedRevision(e.target.value)}><option value="">Revizyon seçin</option>{state.history.map(r=><option key={r.revision} value={r.revision}>r{r.revision} · {r.kind==='MASTER_CANDIDATE'?'Master adayı':'Taslak'} · {r.author} · {r.note}</option>)}</select></label><button className={button} disabled={!selectedRevision} onClick={openRevision}>Revizyonu taslak olarak aç</button><button className={button} disabled={!selectedRevision} onClick={downloadSaved}>Kayıtlı revizyon paketi indir</button></div>
      </section>
      {state.evaluation&&<section className="p-4 rounded-xl border border-amber-800 space-y-2"><h3 className="font-semibold">r{state.revision} reçetesi · {dirty?'Taslak değişti; yeniden kaydedilmeden geçerli değil':state.evaluation.gate.status}</h3><p className="text-sm">{state.evaluation.summary.total_order_yarn_kg.toLocaleString('tr-TR')} kg · {state.evaluation.summary.total_order_cost_tl.toLocaleString('tr-TR')} TL</p><p className="text-xs text-slate-400">{state.evaluation.source}</p><p className="text-xs">Karşılıklı kenar farkı: sağ/sol {state.evaluation.seam.left_right_mismatch_cells} hücre · üst/alt {state.evaluation.seam.top_bottom_mismatch_cells} hücre. {state.evaluation.seam.note}</p><ul className="list-disc pl-5 text-xs text-amber-300">{[...state.evaluation.gate.reasons,...state.evaluation.gate.pending].map(s=><li key={s}>{s}</li>)}</ul><p className="text-xs break-all text-slate-500">Matris SHA-256: {state.evaluation.grid_sha256}</p><p className="text-xs text-amber-300">V1.2 pre-flight ve üretici CAM doğrulaması tamamlanmadan APPROVED durumuna geçilmez. Bu ekrandan tezgâha gönderim yapılmaz.</p></section>}
      {state.evaluation&&<details className="border border-slate-700 rounded-xl p-4"><summary className="cursor-pointer text-sm">r{state.revision} · Renk bazında kayıtlı reçete {dirty?'(açık taslak için güncel değil)':''}</summary><YarnRecipeTable recipe={state.evaluation.recipe} totalCost={state.evaluation.summary.total_order_cost_tl} totalGrossKg={state.evaluation.summary.total_order_yarn_kg} totalBobbins={state.evaluation.recipe.reduce((sum,r)=>sum+r.bobbin_count_required,0)} orderQuantity={state.loom_config?.order_quantity||1}/></details>}
    </fieldset>}
  </section>;
}
