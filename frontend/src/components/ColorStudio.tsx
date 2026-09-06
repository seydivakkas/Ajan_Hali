import React from 'react';
import { Palette, Info, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { ColorMappingItem } from '../types/carpet';

interface ColorStudioProps {
  mappings: ColorMappingItem[];
}

export const ColorStudio: React.FC<ColorStudioProps> = ({ mappings }) => {
  const getDeltaEBadge = (deltaE: number) => {
    if (deltaE < 3.0) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
          <CheckCircle2 className="w-3 h-3" />
          Mükemmel (ΔE {deltaE.toFixed(1)})
        </span>
      );
    } else if (deltaE < 6.0) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
          <Info className="w-3 h-3" />
          Kabul Edilebilir (ΔE {deltaE.toFixed(1)})
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-rose-500/15 text-rose-400 border border-rose-500/30">
          <AlertTriangle className="w-3 h-3" />
          Farklı Ton (ΔE {deltaE.toFixed(1)})
        </span>
      );
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Title & Stats */}
      <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Palette className="w-4 h-4 text-sky-400" />
            CIEDE2000 Renk Kuantalama & Cağlık Eşleşme Stüdyosu
          </h3>
          <p className="text-xs text-slate-400">
            CIE L*a*b* uzayında ISO/CIE 11664-6 standardına göre fiziksel fabrika ipliklerine zorunlu eşleme
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs">
            <span className="text-slate-400">Cağlık Rengi: </span>
            <span className="text-sky-400 font-bold font-mono">{mappings.length} Renk</span>
          </div>
        </div>
      </div>

      {/* Stacked Percentage Visual Bar */}
      <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
        <span className="text-xs font-medium text-slate-300">Yüzey Alanı Dağılım Spektrumu</span>
        <div className="w-full h-7 rounded-lg overflow-hidden flex border border-slate-700 shadow-inner">
          {mappings.map((item) => (
            <div
              key={item.palette_code}
              style={{
                width: `${item.area_percentage}%`,
                backgroundColor: `rgb(${item.mapped_rgb.join(',')})`,
              }}
              className="h-full relative group transition-all"
              title={`${item.palette_code} - ${item.yarn_name} (%${item.area_percentage.toFixed(1)})`}
            >
              <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-1 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900 text-[10px] text-white rounded border border-slate-700 whitespace-nowrap pointer-events-none z-10 shadow-lg">
                {item.palette_code} (%{item.area_percentage.toFixed(1)})
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Color Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {mappings.map((item) => {
          const rgbString = `rgb(${item.mapped_rgb.join(',')})`;
          return (
            <div
              key={item.palette_code}
              className="bg-slate-900/80 rounded-xl border border-slate-800 p-4 flex flex-col gap-3 hover:border-slate-700 transition-all shadow"
            >
              {/* Top Row: Swatch & Code */}
              <div className="flex items-center gap-3">
                <div
                  className="w-12 h-12 rounded-lg border-2 border-slate-700 shadow-md flex-shrink-0"
                  style={{ backgroundColor: rgbString }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold text-sky-400">
                      {item.palette_code}
                    </span>
                    {getDeltaEBadge(item.ciede2000_delta_e_avg)}
                  </div>
                  <h4 className="text-xs font-semibold text-slate-100 truncate mt-0.5">
                    {item.yarn_name}
                  </h4>
                  <p className="text-[11px] text-slate-400 truncate">
                    {item.material}
                  </p>
                </div>
              </div>

              {/* Middle Row: Area Percentage & Progress Bar */}
              <div>
                <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                  <span>Yüzey Kaplama</span>
                  <span className="font-semibold text-slate-200">
                    %{item.area_percentage.toFixed(2)} ({item.pixel_count.toLocaleString()} hücre)
                  </span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-sky-500 rounded-full"
                    style={{ width: `${item.area_percentage}%` }}
                  />
                </div>
              </div>

              {/* Bottom Row: DeltaE Metrics */}
              <div className="pt-2 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-[11px]">
                <div className="bg-slate-800/40 rounded p-1.5 text-center">
                  <span className="text-slate-500 block text-[10px]">Ortalama ΔE₀₀</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {item.ciede2000_delta_e_avg.toFixed(2)}
                  </span>
                </div>
                <div className="bg-slate-800/40 rounded p-1.5 text-center">
                  <span className="text-slate-500 block text-[10px]">Maksimum ΔE₀₀</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {item.ciede2000_delta_e_max.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
