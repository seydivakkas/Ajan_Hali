import React, { useState } from 'react';
import { LoomFormConfig } from '../types/carpet';
type Point = [number, number];
interface Props { src: string; config: LoomFormConfig; onChange: (config: LoomFormConfig) => void; disabled: boolean }

export function PhotoEditor({ src, config, onChange, disabled }: Props) {
  const [mode, setMode] = useState<'corners' | 'repair'>('corners');
  const [start, setStart] = useState<Point | null>(null);
  const corners = config.manual_corners || [];
  const regions = config.repair_regions || [];
  const names = ['Sol üst', 'Sağ üst', 'Sağ alt', 'Sol alt'];
  const point = (event: React.MouseEvent<SVGSVGElement>) => {
    if (disabled) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const p: Point = [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
    if (mode === 'corners' && corners.length < 4) onChange({ ...config, manual_corners: [...corners, p] });
    if (mode === 'repair' && regions.length < 50) {
      if (!start) setStart(p);
      else {
        const region: [number, number, number, number] = [Math.min(start[0],p[0]), Math.min(start[1],p[1]), Math.max(start[0],p[0]), Math.max(start[1],p[1])];
        if (region[2]-region[0] > .002 && region[3]-region[1] > .002) {
          onChange({ ...config, enable_symmetry: true, repair_regions: [...regions, region] });
        }
        setStart(null);
      }
    }
  };
  return <section className="rounded-xl border border-slate-700 bg-slate-950 p-3 space-y-3">
    <h3 className="text-sm font-semibold">Fotoğraf düzeltme</h3>
    <div className="flex gap-2">
      <button type="button" disabled={disabled} aria-pressed={mode === 'corners'} className={`text-xs rounded px-2 py-2 ${mode === 'corners' ? 'bg-sky-600' : 'bg-slate-800'}`} onClick={() => { setMode('corners'); setStart(null); }}>Dört köşe</button>
      <button type="button" disabled={disabled} aria-pressed={mode === 'repair'} className={`text-xs rounded px-2 py-2 ${mode === 'repair' ? 'bg-sky-600' : 'bg-slate-800'}`} onClick={() => { setMode('repair'); setStart(null); }}>Onarım alanı</button>
    </div>
    <p className="text-xs text-slate-400" aria-live="polite">{mode === 'corners' ? corners.length < 4 ? `Fotoğrafta ${names[corners.length]} köşeye dokunun (${corners.length}/4). Seçmezseniz otomatik tespit kullanılır.` : 'Dört köşe seçildi. Değiştirmek için geri alın.' : start ? 'Dikdörtgenin karşı köşesine dokunun.' : 'Etiket veya kapalı alanı iki karşı köşesine dokunarak işaretleyin. İşaretli alanlar otomatik maskenin yerine kullanılır.'}</p>
    <div className="relative">
      <img src={src} alt="Düzeltilecek halı fotoğrafı" className="w-full block rounded" draggable={false} />
      <svg className="absolute inset-0 w-full h-full cursor-crosshair" viewBox="0 0 1000 1000" preserveAspectRatio="none" onClick={point} aria-label="Köşe ve onarım alanı seçim yüzeyi">
        {regions.map((r,i) => <rect key={i} x={r[0]*1000} y={r[1]*1000} width={(r[2]-r[0])*1000} height={(r[3]-r[1])*1000} fill="#f43f5e55" stroke="#fb7185" strokeWidth="4" />)}
        {corners.length > 1 && <polyline points={corners.map(p => `${p[0]*1000},${p[1]*1000}`).join(' ') + (corners.length === 4 ? ` ${corners[0][0]*1000},${corners[0][1]*1000}` : '')} fill="none" stroke="#38bdf8" strokeWidth="5" />}
        {corners.map((p,i) => <g key={i}><circle cx={p[0]*1000} cy={p[1]*1000} r="14" fill="#38bdf8" /><text x={p[0]*1000+18} y={p[1]*1000+25} fill="white" fontSize="45">{i+1}</text></g>)}
        {start && <circle cx={start[0]*1000} cy={start[1]*1000} r="12" fill="#fb7185" />}
      </svg>
    </div>
    <div className="flex flex-wrap gap-2 text-xs">
      <button type="button" disabled={disabled} className="underline" onClick={() => { setStart(null); onChange(mode === 'corners' ? { ...config, manual_corners: corners.length > 1 ? corners.slice(0,-1) : undefined } : { ...config, repair_regions: regions.slice(0,-1) }); }}>Son seçimi geri al</button>
      <button type="button" disabled={disabled} className="underline" onClick={() => { setStart(null); onChange({ ...config, manual_corners: undefined, repair_regions: [] }); }}>Seçimleri temizle</button>
    </div>
    <p className="text-xs text-slate-500">{regions.length} onarım bölgesi · Yeni fotoğraf seçildiğinde işaretler temizlenir.</p>
  </section>;
}
