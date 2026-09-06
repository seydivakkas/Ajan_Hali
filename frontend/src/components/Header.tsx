import React from 'react';
import { Cpu, Activity, Play, CheckCircle2, AlertCircle } from 'lucide-react';

interface HeaderProps {
  backendOnline: boolean;
  activeJobId: string | null;
}

export const Header: React.FC<HeaderProps> = ({
  backendOnline,
  activeJobId,
}) => {
  return (
    <header className="border-b border-slate-800 bg-industrial-900/90 backdrop-blur sticky top-0 z-50 px-6 py-3.5">
      <div className="flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand & System Identity */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 shadow-inner">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-lg text-white tracking-wide">
                AJAN HALI <span className="text-xs px-2 py-0.5 rounded bg-sky-500/20 text-sky-400 font-mono font-normal border border-sky-500/30">CAD/CAM STÜDYOSU</span>
              </h1>
              <span className="text-xs text-slate-500 hidden sm:inline">v1.0 Industrial</span>
            </div>
            <p className="text-xs text-slate-400">
              Rakip Halı Fotoğrafından CIEDE2000 Renk Kuantalama, Tezgâh CAD & İplik Reçetesi
            </p>
          </div>
        </div>

        {/* Status Chips & Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Active Job ID Badge */}
          {activeJobId && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-xs font-mono text-slate-300">
              <span className="text-slate-500">İŞ ID:</span>
              <span className="text-sky-400 font-semibold">{activeJobId}</span>
            </div>
          )}

          {/* Backend Status Indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 text-xs">
            <Activity className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400 hidden lg:inline">FastAPI Motor:</span>
            {backendOnline ? (
              <span className="flex items-center gap-1 text-emerald-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                Bağlı
              </span>
            ) : (
              <span className="flex items-center gap-1 text-rose-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-rose-400"></span>
                Bağlantı Yok
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
