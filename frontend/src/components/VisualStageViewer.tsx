import React, { useState } from 'react';
import { Layers, ZoomIn, Eye, SplitSquareVertical } from 'lucide-react';
import { AnalysisPipelineResult } from '../types/carpet';
import { resolveImageUrl } from '../services/api';
import { BeforeAfterSlider } from './BeforeAfterSlider';

interface VisualStageViewerProps {
  data: AnalysisPipelineResult;
}

export const VisualStageViewer: React.FC<VisualStageViewerProps> = ({ data }) => {
  const [selectedStage, setSelectedStage] = useState<number>(3); // Default to quantized final
  const [showSlider, setShowSlider] = useState<boolean>(false);

  const stages = [
    {
      id: 0,
      title: '1. Ham Fotoğraf',
      badge: 'Girdi',
      description: 'Saha/Mağaza ortamında çekilen orijinal perspektifli fotoğraf',
      url: resolveImageUrl(data.input_image_path),
    },
    {
      id: 1,
      title: '2. Homografi Rektifiye',
      badge: 'DLT 4-Köşe',
      description: 'Ortogonal üstten bakış düzlemine oturtulmuş ve dengelenmiş görünüm',
      url: resolveImageUrl(data.rectified_image_path),
    },
    {
      id: 2,
      title: '3. AI Simetri Tamamlama',
      badge: 'D4 Ayna & Doku',
      description: 'Eksik veya mobilyayla kapalı alanların dihedral simetriyle onarımı',
      url: resolveImageUrl(data.completed_pattern_path),
    },
    {
      id: 3,
      title: '4. Fabrika Paletine Eşleme',
      badge: 'CIEDE2000 Kuantalama',
      description: 'Tezgâh cağlığındaki gerçek fiziksel iplik renklerine kuantalanmış üretim deseni',
      url: resolveImageUrl(data.quantized_preview_path),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {data.repair_mask_path && <details className="rounded-xl border border-slate-800 p-4 text-xs text-slate-300">
        <summary className="cursor-pointer">Onarım maskesi ve köşe kaynağı · {data.preprocessing_metadata?.segmentation_engine || 'Eski kayıt'}</summary>
        <p className="my-2">Beyaz alanlar onarım için seçilen bölgelerdir. Onarım kapalıysa uygulanmaz.</p>
        <img src={resolveImageUrl(data.repair_mask_path)} alt="Perspektifi düzeltilmiş onarım maskesi" className="max-h-72 max-w-full" />
      </details>}
      {/* View Switcher Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-sky-400" />
            4 Kademeli Halı Rekonstrüksiyon Süreci
          </h3>
          <p className="text-xs text-slate-400">
            Aşama aşama homografi, desen onarımı ve CIEDE2000 renk kuantalama sonuçları
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSlider(!showSlider)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
              showSlider
                ? 'bg-sky-500 text-slate-950 font-semibold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700'
            }`}
          >
            <SplitSquareVertical className="w-3.5 h-3.5" />
            <span>{showSlider ? 'Galeri Görünümüne Dön' : 'A/B Öncesi / Sonrası Karşılaştır'}</span>
          </button>
        </div>
      </div>

      {showSlider ? (
        <BeforeAfterSlider
          beforeImage={stages[1].url}
          afterImage={stages[3].url}
          beforeLabel="Rektifiye Orijinal Halı"
          afterLabel="Fabrika Paletine Kuantalanmış Desen (CIEDE2000)"
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {stages.map((stage) => {
            const isSelected = selectedStage === stage.id;
            return (
              <div
                key={stage.id}
                onClick={() => setSelectedStage(stage.id)}
                className={`group cursor-pointer rounded-xl overflow-hidden border transition-all flex flex-col bg-slate-900/80 ${
                  isSelected
                    ? 'border-sky-500 ring-1 ring-sky-500 shadow-lg shadow-sky-500/10'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                {/* Header */}
                <div className="p-3 border-b border-slate-800 flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">{stage.title}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 border border-slate-700 font-mono">
                    {stage.badge}
                  </span>
                </div>

                {/* Thumbnail Container */}
                <div className="relative aspect-[3/4] bg-black/40 overflow-hidden flex items-center justify-center p-2">
                  <img
                    src={stage.url}
                    alt={stage.title}
                    className="w-full h-full object-contain rounded transition-transform duration-300 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <span className="px-2.5 py-1 rounded bg-sky-500 text-slate-950 font-semibold text-[11px] flex items-center gap-1 shadow">
                      <ZoomIn className="w-3 h-3" />
                      Büyük İncele
                    </span>
                  </div>
                </div>

                {/* Footer description */}
                <div className="p-3 text-[11px] text-slate-400 border-t border-slate-800/80 bg-slate-900/40">
                  {stage.description}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Selected Large Preview Modal or Expansion */}
      {!showSlider && (
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 flex flex-col items-center gap-3">
          <div className="w-full flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h4 className="text-sm font-semibold text-white">
                Büyük Önizleme: {stages[selectedStage].title}
              </h4>
              <p className="text-xs text-slate-400">
                {stages[selectedStage].description}
              </p>
            </div>
            <a
              href={stages[selectedStage].url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1"
            >
              <Eye className="w-3.5 h-3.5" />
              Yeni Sekmede Aç
            </a>
          </div>

          <div className="w-full max-w-2xl max-h-[600px] overflow-hidden rounded-lg bg-black/60 flex items-center justify-center border border-slate-800 p-2">
            <img
              src={stages[selectedStage].url}
              alt={stages[selectedStage].title}
              className="max-h-[560px] object-contain rounded shadow-2xl"
            />
          </div>
        </div>
      )}
    </div>
  );
};
