import React, { useState, useEffect } from 'react';
import {
  Layers,
  Palette,
  FileCode,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  AlertCircle,
  Clock,
  Compass,
} from 'lucide-react';

import { LoomFormConfig, AnalysisPipelineResult } from './types/carpet';
import { checkBackendHealth, runCarpetAnalysis, fetchJobs, fetchJob, JobSummary } from './services/api';
import { FactorySettingsPanel } from './components/FactorySettingsPanel';
import { DesignerTools } from './components/DesignerTools';
import { ProductionStudio } from './components/ProductionStudio';
import { FactorySettings, fetchSettings, deleteDemoJobs } from './services/settings';
import { Header } from './components/Header';
import { ConfigSidebar } from './components/ConfigSidebar';
import { VisualStageViewer } from './components/VisualStageViewer';
import { ColorStudio } from './components/ColorStudio';
import { CurrentQuote } from './components/CurrentQuote';
import { YarnRecipeTable } from './components/YarnRecipeTable';
import { CadExportPanel } from './components/CadExportPanel';
import { DesignReviewPanel } from './components/DesignReviewPanel';
import { AuditScoreCard } from './components/AuditScoreCard';

export const App: React.FC = () => {
  const [factory, setFactory] = useState<FactorySettings | null>(null);
  const [workspace, setWorkspace] = useState<'analysis' | 'settings' | 'tools' | 'studio'>('analysis');
  const [studioDirty, setStudioDirty] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'visual' | 'colors' | 'yarn' | 'cad' | 'audit'>('visual');
  const [result, setResult] = useState<AnalysisPipelineResult | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [config, setConfig] = useState<LoomFormConfig>({
    weave_structure_factor: Number.NaN,
    anchor_length_mm: Number.NaN,
    width_cm: Number.NaN,
    length_cm: Number.NaN,
    reed_density: Number.NaN,
    pick_density: Number.NaN,
    pile_height_mm: Number.NaN,
    max_colors: Number.NaN,
    order_quantity: Number.NaN,
    waste_coefficient: Number.NaN,
    enable_symmetry: true,
    enable_sam: true,
    enable_dereflection: true,
    symmetry_mode: 'QUADRANT_4FOLD',
  });

  useEffect(() => {
    checkBackendHealth().then(() => setBackendOnline(true)).catch(() => setBackendOnline(false));
    fetchJobs().then(setJobs).catch(() => {});
    fetchSettings().then(data => { setFactory(data); if (!data.yarns.length) setWorkspace("settings"); }).catch(e => setError(e.message));
  }, []);

  useEffect(() => {
    if (!isLoading) return;
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isLoading]);

  useEffect(() => {
    if (result) fetchJobs().then(setJobs).catch(() => {});
  }, [result]);

  const handleOpenJob = async (id: string) => {
    if (!id) return;
    if(studioDirty&&!window.confirm('Studio taslağı kaydedilmedi. Başka analize geçilip değişiklikler bırakılsın mı?'))return;
    setIsLoading(true);
    setError(null);
    try { setResult(await fetchJob(id)); }
    catch (err: any) { setError(err.message); }
    finally { setIsLoading(false); }
  };

  const handleAnalyze = async (file: File) => {
    if(studioDirty&&!window.confirm('Studio taslağı kaydedilmedi. Yeni analiz sonucuyla değiştirmek istiyor musunuz?'))return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await runCarpetAnalysis(file, config);
      setResult(data);
      setActiveTab('visual');
    } catch (err: any) {
      setError(err.message || 'Halı analizi sırasında beklenmeyen bir hata oluştu.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-industrial-950 text-slate-100 font-sans">
      {/* Top Navigation */}
      <Header
        backendOnline={backendOnline}
        activeJobId={result ? result.job_id : null}

      />

      <nav className="flex flex-wrap items-center gap-3 px-6 py-3 border-b border-slate-800" aria-label="Çalışma alanı">
        <button disabled={isLoading} onClick={() => setWorkspace('analysis')} className={`px-4 py-2 rounded-lg text-sm ${workspace === 'analysis' ? 'bg-sky-600' : 'bg-slate-800'}`}>Analiz stüdyosu</button>
        <button disabled={isLoading} onClick={() => setWorkspace('tools')} className={`px-4 py-2 rounded-lg text-sm ${workspace === 'tools' ? 'bg-sky-600' : 'bg-slate-800'}`}>Desinatör araçları</button>
        <button disabled={isLoading} onClick={() => setWorkspace('studio')} className={`px-4 py-2 rounded-lg text-sm ${workspace === 'studio' ? 'bg-sky-600' : 'bg-slate-800'}`}>Desen Studio · V1.1</button>
        <button disabled={isLoading} onClick={() => setWorkspace('settings')} className={`px-4 py-2 rounded-lg text-sm ${workspace === 'settings' ? 'bg-sky-600' : 'bg-slate-800'}`}>Fabrika ayarları · İplik / fiyat / tezgâh</button>
        <span className="hidden md:inline text-xs text-slate-400">{factory?.company_name || 'Şirket bilgileri bekleniyor'}</span>
      </nav>
      {factory?.yarns.some(y=>y.is_demo) && <div className="px-6 py-3 bg-amber-950/40 text-amber-300 text-sm">DEMO aktif — Envanter sentetik kayıt içeriyor. Yeni analizler eğitim amaçlıdır; gerçek kayıtlarınız silinmez.
        <button disabled={isLoading} className="ml-3 underline" onClick={()=>setConfig({...config,width_cm:160,length_cm:230,reed_density:100,pick_density:100,pile_height_mm:11.5,max_colors:4,order_quantity:1,waste_coefficient:0.07,weave_structure_factor:1,anchor_length_mm:2,enable_sam:false})}>Örnek test parametrelerini doldur</button>
        <span className="block text-xs mt-1">Örnek parametreler: 160 × 230 cm, 100 tarak/m, 100 atkı/m, 11,5 mm hav, 1 adet, %7 fire. Fabrika tezgâh ayarı değildir.</span>
      </div>}
      <main className={`${workspace === 'settings' ? '' : 'hidden'} p-6 max-w-7xl w-full mx-auto`}>{factory ? <FactorySettingsPanel initial={factory} onSaved={setFactory} /> : <p role="status">{error || 'Ayarlar yükleniyor…'}</p>}</main>
      <main className={`${workspace === 'tools' ? '' : 'hidden'} p-6 max-w-7xl w-full mx-auto`}><DesignerTools result={result} onOpen={destination=>{if(destination==='settings')setWorkspace('settings');else{setWorkspace('analysis');setActiveTab(destination);}}}/></main>
      {/* Main Workspace Layout */}
      <main className={`${workspace==='studio'?'':'hidden'} p-6 max-w-[1800px] w-full mx-auto`}><ProductionStudio jobId={result?.job_id||null} onDirty={setStudioDirty}/></main>
      <div className={`${workspace === "analysis" ? "flex" : "hidden"} flex-1 flex-col lg:flex-row overflow-hidden`}>
        {/* Left Sidebar: Form & Upload Controls */}
        <ConfigSidebar
          config={config}
          onChangeConfig={setConfig}
          onAnalyze={handleAnalyze}
          isLoading={isLoading}
          canAnalyze={!!factory?.yarns.length && (!!factory?.company_name || factory.yarns.some(y=>y.is_demo))}
        />

        {/* Right Content Area */}
        <main className="flex-1 flex flex-col p-6 overflow-y-auto bg-slate-950">
          <section className="mb-5 rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="text-sm font-semibold" htmlFor="job-history">Analiz geçmişi</label>
              <select id="job-history" disabled={isLoading} value={result?.job_id || ''}
                onChange={e => handleOpenJob(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs max-w-full">
                <option value="">Kayıtlı analiz seçin ({jobs.length})</option>
                {jobs.map(job => <option key={job.job_id} value={job.job_id}>
                  {job.data_source === 'DEMO_SYNTHETIC' ? 'DEMO · ' : ''}{job.job_id} · {job.dimensions.join(' × ')} cm · {job.created_at ? new Date(job.created_at).toLocaleString('tr-TR') : 'Eski kayıt'}
                </option>)}
              </select>
              <button disabled={isLoading} className="text-xs text-rose-300 border border-rose-900 p-2 rounded" onClick={async()=>{
                if(studioDirty&&!window.confirm('Studio taslağı kaydedilmedi. Demo analizlerini silmek açık taslağı da kaldırabilir. Devam edilsin mi?'))return;
                setIsLoading(true); setError(null);
                try { await deleteDemoJobs(); if(result?.data_source==='DEMO_SYNTHETIC') setResult(null); setJobs(await fetchJobs()); }
                catch(e:any) { setError(e.message); } finally { setIsLoading(false); }
              }}>Demo analizlerini ve dosyalarını sil</button>
            </div>
            <p className="text-xs text-amber-300">ERP: bağlı değil · Tezgâha gönderim: kapalı · EP / JC5: doğrulanmamış prototip</p>
            {result && <p className="text-xs text-slate-400">
              {result.data_source === 'DEMO_SYNTHETIC' ? 'DEMO — Sentetik veriyle hesaplandı. Üretimde kullanmayın.' : 'Kullanıcı paletiyle hesaplanan sonuç'} ·
              {result.loom_config ? ` ${result.loom_config.order_quantity} adet, %${Math.round(result.loom_config.waste_coefficient * 100)} fire` : ' Ayar kaydı bulunmayan eski analiz'}.
              Soldaki ayarlar yeni analiz için geçerlidir. İplik maliyeti tahminidir; işçilik ve enerji dahil değildir.
            </p>}
          </section>
          {isLoading && <div role="status" className="mb-5 p-4 rounded-xl bg-sky-500/10 text-sky-300 text-sm">
            İşlem sürüyor · {elapsed} saniye. Sonuç hazır olduğunda otomatik gösterilecek.
          </div>}
          {/* Error Banner if any */}
          {error && (
            <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{error}</span>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-rose-400 hover:text-rose-200 underline text-xs"
              >
                Kapat
              </button>
            </div>
          )}

          {result ? (
            <div className="flex flex-col gap-6">
              {/* Top Overview Ribbon */}
              <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex items-center gap-2">
                    <Compass className="w-4 h-4 text-sky-400" />
                    <span className="text-xs text-slate-400">Üretim Ebadı:</span>
                    <span className="text-xs font-mono font-bold text-white">
                      {result.carpet_dimensions_cm[0]} × {result.carpet_dimensions_cm[1]} cm
                    </span>
                  </div>

                  <div className="h-4 w-px bg-slate-800 hidden sm:block" />

                  <div>
                    <span className="text-xs text-slate-400">Toplam Sipariş Alanı: </span>
                    <span className="text-xs font-mono font-bold text-white">
                      {result.total_area_sqm.toFixed(1)} m²
                    </span>
                  </div>

                  <div className="h-4 w-px bg-slate-800 hidden sm:block" />

                  <div>
                    <span className="text-xs text-slate-400">Tezgâh Hücre Oranı: </span>
                    <span className="text-xs font-mono font-bold text-sky-400">
                      {result.grid_resolution_cells[0]} × {result.grid_resolution_cells[1]} (Anizotropik {result.loom_aspect_ratio.toFixed(3)})
                    </span>
                  </div>
                </div>

                {/* Audit Pill */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Hazırlık Skoru:</span>
                  <span className="px-2.5 py-1 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-bold font-mono">
                    {Math.round(result.production_audit.overall_readiness_score)} / 100
                  </span>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="border-b border-slate-800 flex items-center gap-2 overflow-x-auto pb-px">
                <button
                  onClick={() => setActiveTab('visual')}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all whitespace-nowrap cursor-pointer ${
                    activeTab === 'visual'
                      ? 'bg-slate-900 text-sky-400 border-t-2 border-sky-400 border-x border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <Layers className="w-4 h-4" />
                  <span>Görsel Rekonstrüksiyon</span>
                </button>

                <button
                  onClick={() => setActiveTab('colors')}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all whitespace-nowrap cursor-pointer ${
                    activeTab === 'colors'
                      ? 'bg-slate-900 text-sky-400 border-t-2 border-sky-400 border-x border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <Palette className="w-4 h-4" />
                  <span>CIEDE2000 Renk Stüdyosu</span>
                  <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] font-mono text-slate-300">
                    {result.color_mappings.length}
                  </span>
                </button>

                <button
                  onClick={() => setActiveTab('yarn')}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all whitespace-nowrap cursor-pointer ${
                    activeTab === 'yarn'
                      ? 'bg-slate-900 text-sky-400 border-t-2 border-sky-400 border-x border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <ShoppingBag className="w-4 h-4" />
                  <span>İplik Reçetesi & Stok</span>
                </button>

                <button
                  onClick={() => setActiveTab('cad')}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all whitespace-nowrap cursor-pointer ${
                    activeTab === 'cad'
                      ? 'bg-slate-900 text-sky-400 border-t-2 border-sky-400 border-x border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <FileCode className="w-4 h-4" />
                  <span>CAD / CAM İhracı</span>
                </button>

                <button
                  onClick={() => setActiveTab('audit')}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all whitespace-nowrap cursor-pointer ${
                    activeTab === 'audit'
                      ? 'bg-slate-900 text-sky-400 border-t-2 border-sky-400 border-x border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>Üretim Karnesi & Riskler</span>
                </button>
              </div>

              {/* Tab Contents */}
              <div className="pt-2">
                {activeTab === 'visual' && <VisualStageViewer data={result} />}
                {activeTab === 'colors' && <ColorStudio mappings={result.color_mappings} />}
                {activeTab === 'yarn' && (
                  <><YarnRecipeTable
                    recipe={result.yarn_recipe}
                    totalCost={result.total_production_cost_tl}
                    totalGrossKg={result.total_gross_yarn_weight_kg}
                    totalBobbins={result.total_bobbins_required}
                    orderQuantity={result.loom_config?.order_quantity ?? Math.max(1, Math.round(result.total_area_sqm / (result.carpet_dimensions_cm[0] * result.carpet_dimensions_cm[1] / 10000)))}
                  />
                  <CurrentQuote key={result.job_id} data={result} /></>
                )}
                {activeTab === 'cad' && <CadExportPanel data={result} />}
                {activeTab === 'audit' && <><AuditScoreCard audit={result.production_audit} /><DesignReviewPanel key={result.job_id} jobId={result.job_id} /></>}
              </div>
            </div>
          ) : (
            /* Empty State */
            <div className="flex-1 flex flex-col items-center justify-center py-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 mb-4 shadow-lg">
                <Sparkles className="w-8 h-8" />
              </div>
              <h3 className="text-base font-semibold text-white">Henüz Bir Halı Analiz Edilmedi</h3>
              <p className="text-xs text-slate-400 max-w-md mt-1 mb-6">
                Önce fabrika ayarlarında iplik bilgilerinizi kaydedin. Ardından fotoğrafınızı yükleyip gerçek tezgâh ve sipariş parametrelerini girin.
              </p>
              <button
                onClick={() => setWorkspace("settings")}
                disabled={isLoading}
                className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer shadow"
              >
                <Clock className="w-4 h-4" />
                <span>Fabrika bilgilerini düzenle</span>
              </button>
            </div>
          )}
        </main>
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-industrial-900/80 px-6 py-3 text-center text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span>ÖZEL LİSANS — TÜM HAKLAR SAKLIDIR</span>
          <span>•</span>
          <span>Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas)</span>
        </div>
        <div className="text-[11px] text-slate-600 font-mono">
          ISO/CIE 11664-6:2014 CIEDE2000 • AutoCAD DXF R12 • Electronic Jacquard CAM
        </div>
      </footer>
    </div>
  );
};
