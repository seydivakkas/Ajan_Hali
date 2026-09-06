import React, { useState } from 'react';
import { Download, FileCode, Layers, FileText, Grid, Sparkles, Check, Cpu } from 'lucide-react';
import { AnalysisPipelineResult } from '../types/carpet';
import { getDownloadUrl, resolveImageUrl } from '../services/api';

interface CadExportPanelProps {
  data: AnalysisPipelineResult;
}

export const CadExportPanel: React.FC<CadExportPanelProps> = ({ data }) => {
  const [downloaded, setDownloaded] = useState<string | null>(null);

  const handleDownload = (format: 'dxf' | 'svg' | 'loom' | 'vdw' | 'staubli' | 'report') => {
    const url = getDownloadUrl(data.job_id, format);
    window.open(url, '_blank');
    setDownloaded(format);
    setTimeout(() => setDownloaded(null), 3000);
  };

  const svgUrl = resolveImageUrl(data.svg_export_path);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <FileCode className="w-4 h-4 text-sky-400" />
            Teknik CAD / CAM & Tezgâh İhracat Merkezi
          </h3>
          <p className="text-xs text-slate-400">
            CAD inceleme dosyaları ve deneysel CAM çıktıları; hazırlık skoru tezgâh uyumluluk onayı değildir.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>Tezgâh Matris Boyutu:</span>
          <span className="text-sky-400 font-bold">
            {data.grid_resolution_cells[0]} × {data.grid_resolution_cells[1]} Hücre
          </span>
        </div>
      </div>

      {/* Export Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* 1. DXF Card */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
              <Layers className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-sky-400 font-mono">
              AutoCAD R12
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">AutoCAD DXF</h4>
            <p className="text-xs text-slate-400 mt-1">
              Her iplik rengi için ayrı CAD katmanında kapalı kontur poligonları (POLYLINE).
            </p>
          </div>

          <button
            onClick={() => handleDownload('dxf')}
            className="w-full py-2 px-3 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'dxf' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>DXF Dosyasını İndir</span>
              </>
            )}
          </button>
        </div>

        {/* 2. SVG Card */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-amber-400 font-mono">
              Vektörel SVG
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">Vektörel Çizim (SVG)</h4>
            <p className="text-xs text-slate-400 mt-1">
              Ölçeklenebilir vektör formatı; katalog baskısı ve desinatör incelemesi için tam çözünürlüklü vektör.
            </p>
          </div>

          <button
            onClick={() => handleDownload('svg')}
            className="w-full py-2 px-3 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'svg' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>SVG Çizimini İndir</span>
              </>
            )}
          </button>
        </div>

        {/* 3. Jacquard Loom Matrix Card */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Grid className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-emerald-400 font-mono">
              Elektronik Jakar
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">Jakar Tezgâh Matrisi</h4>
            <p className="text-xs text-slate-400 mt-1">
              Satır satır hücre bazlı iplik kontrol kodları matrisi (.DAT/.EP/.TXT formatı).
            </p>
          </div>

          <button
            onClick={() => handleDownload('loom')}
            className="w-full py-2 px-3 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'loom' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>Matris Dosyasını İndir</span>
              </>
            )}
          </button>
        </div>

        {/* 4. Van de Wiele CAM (.EP) */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
              <Cpu className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-rose-400 font-mono">
              Van de Wiele .EP
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">Van de Wiele (.EP)</h4>
            <p className="text-xs text-slate-400 mt-1">
              Deneysel ikili desen dosyası. Üretici kontrolör uyumluluğu doğrulanmadı; doğrudan üretimde kullanmayın.
            </p>
          </div>

          <button
            onClick={() => handleDownload('vdw')}
            className="w-full py-2 px-3 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'vdw' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>VdW .EP İndir</span>
              </>
            )}
          </button>
        </div>

        {/* 5. Stäubli Jacquard (.JC5) */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Layers className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-cyan-400 font-mono">
              Stäubli .JC5
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">Stäubli (.JC5)</h4>
            <p className="text-xs text-slate-400 mt-1">
              Deneysel metin matrisi. Stäubli kontrolör uyumluluğu doğrulanmadı; desinatör incelemesi içindir.
            </p>
          </div>

          <button
            onClick={() => handleDownload('staubli')}
            className="w-full py-2 px-3 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'staubli' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>Stäubli .JC5 İndir</span>
              </>
            )}
          </button>
        </div>

        {/* 6. Analysis Report JSON Card */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition-all">
          <div className="flex items-start justify-between">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
              <FileText className="w-5 h-5" />
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-purple-400 font-mono">
              JSON Rapor
            </span>
          </div>

          <div>
            <h4 className="text-sm font-bold text-white">Analiz & İplik Raporu</h4>
            <p className="text-xs text-slate-400 mt-1">
              ERP/Satın alma sistemlerine aktarılabilir tam teknik karne ve reçete veri yapısı.
            </p>
          </div>

          <button
            onClick={() => handleDownload('report')}
            className="w-full py-2 px-3 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/30 text-purple-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
          >
            {downloaded === 'report' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>İndirme açıldı</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                <span>JSON Raporunu İndir</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* SVG Live Preview Card */}
      {svgUrl && (
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h4 className="text-sm font-semibold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-sky-400" />
              Canlı Vektörel SVG Önizlemesi
            </h4>
            <span className="text-xs text-slate-400 font-mono">
              En: {data.carpet_dimensions_cm[0]}cm × Boy: {data.carpet_dimensions_cm[1]}cm
            </span>
          </div>
          <div className="w-full flex justify-center bg-black/40 rounded-lg p-4 border border-slate-800/80 max-h-[500px] overflow-hidden">
            <img
              src={svgUrl}
              alt="SVG Preview"
              className="max-h-[460px] object-contain rounded shadow"
            />
          </div>
        </div>
      )}
    </div>
  );
};
