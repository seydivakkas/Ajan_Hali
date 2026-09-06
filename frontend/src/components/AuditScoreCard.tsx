import React from 'react';
import { ShieldCheck, AlertTriangle, AlertOctagon, Info, CheckCircle2, Wrench } from 'lucide-react';
import { ProductionAuditScore } from '../types/carpet';

interface AuditScoreCardProps {
  audit: ProductionAuditScore;
}

export const AuditScoreCard: React.FC<AuditScoreCardProps> = ({ audit }) => {
  const getStatusBadge = () => {
    switch (audit.status) {
      case 'READY':
        return {
          label: 'ÜRETİME HAZIR (READY)',
          color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-400" />,
        };
      case 'READY_WITH_WARNING':
        return {
          label: 'UYARI İLE ÜRETİLEBİLİR (READY_WITH_WARNING)',
          color: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
          icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
        };
      case 'REVIEW_REQUIRED':
        return {
          label: 'DESİNATÖR ONAYI GEREKİR (REVIEW_REQUIRED)',
          color: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
          icon: <Info className="w-5 h-5 text-orange-400" />,
        };
      default:
        return {
          label: 'ÜRETİM İÇİN GÜVENLİ DEĞİL (NOT_PRODUCTION_SAFE)',
          color: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
          icon: <AlertOctagon className="w-5 h-5 text-rose-400" />,
        };
    }
  };

  const badge = getStatusBadge();

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner: Score & Overall Decision */}
      <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-6 flex flex-col md:flex-row items-center justify-between gap-6 shadow">
        <div className="flex items-center gap-5">
          {/* Radial / Circle Score Indicator */}
          <div className="relative w-24 h-24 rounded-full border-4 border-slate-800 flex items-center justify-center bg-slate-950 shadow-inner">
            <div className="text-center">
              <span className="text-2xl font-black font-mono text-white block">
                {Math.round(audit.overall_readiness_score)}
              </span>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">
                / 100 Skor
              </span>
            </div>
          </div>

          <div>
            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold block">
              Endüstriyel Üretim Hazırlık Karnesi
            </span>
            <div className="mt-1 flex items-center gap-2">
              <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-lg text-xs font-bold border ${badge.color}`}>
                {badge.icon}
                {badge.label}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-2 max-w-lg">
              Tezgâh parametreleri, CIEDE2000 renk toleransları, desen simetrisi ve stok uygunluğunun birleşik mühendislik değerlendirmesi.
            </p>
          </div>
        </div>

        {/* DeltaE Summary */}
        <div className="grid grid-cols-3 gap-3 w-full md:w-auto border-t md:border-t-0 md:border-l border-slate-800 pt-4 md:pt-0 md:pl-6">
          <div className="bg-slate-800/50 rounded-lg p-2.5 text-center min-w-[90px]">
            <span className="text-[10px] text-slate-400 block">Ortalama ΔE₀₀</span>
            <span className="text-sm font-bold font-mono text-sky-400">
              {audit.delta_e_avg.toFixed(2)}
            </span>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-2.5 text-center min-w-[90px]">
            <span className="text-[10px] text-slate-400 block">p95 ΔE₀₀</span>
            <span className="text-sm font-bold font-mono text-amber-400">
              {audit.delta_e_p95.toFixed(2)}
            </span>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-2.5 text-center min-w-[90px]">
            <span className="text-[10px] text-slate-400 block">Maksimum ΔE₀₀</span>
            <span className="text-sm font-bold font-mono text-rose-400">
              {audit.delta_e_max.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Sub-Score Bars */}
      <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <div className="flex justify-between text-xs text-slate-300 mb-1">
            <span>Girdi Görüntü Kalitesi</span>
            <span className="font-mono font-bold">%{Math.round(audit.input_quality_score)}</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-sky-500 rounded-full"
              style={{ width: `${audit.input_quality_score}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-xs text-slate-300 mb-1">
            <span>Segmentasyon Güveni</span>
            <span className="font-mono font-bold">%{Math.round(audit.segmentation_confidence)}</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full"
              style={{ width: `${audit.segmentation_confidence}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-xs text-slate-300 mb-1">
            <span>Simetri & Tamamlama</span>
            <span className="font-mono font-bold">%{Math.round(audit.completion_confidence)}</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-purple-500 rounded-full"
              style={{ width: `${audit.completion_confidence}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-xs text-slate-300 mb-1">
            <span>Renk Sadakati (Fidelity)</span>
            <span className="font-mono font-bold">%{Math.round(audit.color_fidelity_score)}</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-amber-500 rounded-full"
              style={{ width: `${audit.color_fidelity_score}%` }}
            />
          </div>
        </div>
      </div>

      {/* Risks & Recommendations */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Risk Flags */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col gap-3">
          <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Tespit Edilen Risk Bayrakları
          </h4>
          {audit.risk_flags.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-emerald-400 py-3">
              <CheckCircle2 className="w-4 h-4" />
              <span>Hiçbir kritik risk bayrağı tespit edilmedi.</span>
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {audit.risk_flags.map((flag, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300"
                >
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <span>{flag}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Technical Recommendations */}
        <div className="bg-slate-900/80 rounded-xl border border-slate-800 p-5 flex flex-col gap-3">
          <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <Wrench className="w-4 h-4 text-sky-400" />
            Teknik & Tezgâh Önerileri
          </h4>
          {audit.technical_recommendations.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-slate-400 py-3">
              <Info className="w-4 h-4" />
              <span>Standart üretim parametreleri uygulanabilir.</span>
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {audit.technical_recommendations.map((rec, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 p-2.5 rounded-lg bg-sky-500/10 border border-sky-500/20 text-xs text-sky-300"
                >
                  <CheckCircle2 className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};
