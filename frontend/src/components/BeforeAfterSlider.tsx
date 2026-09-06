import React, { useState, useRef, useCallback } from 'react';
import { ChevronsLeftRight } from 'lucide-react';

interface BeforeAfterSliderProps {
  beforeImage: string;
  afterImage: string;
  beforeLabel?: string;
  afterLabel?: string;
}

export const BeforeAfterSlider: React.FC<BeforeAfterSliderProps> = ({
  beforeImage,
  afterImage,
  beforeLabel = 'Orijinal Rektifiye',
  afterLabel = 'Fabrika Paleti (CIEDE2000)',
}) => {
  const [sliderPos, setSliderPos] = useState<number>(50);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMove = useCallback(
    (clientX: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const percentage = Math.max(0, Math.min(100, (x / rect.width) * 100));
      setSliderPos(percentage);
    },
    []
  );

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches[0]) handleMove(e.touches[0].clientX);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) handleMove(e.clientX);
  };

  return (
    <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 flex flex-col items-center gap-4">
      <div className="flex items-center justify-between w-full text-xs text-slate-400">
        <span className="font-semibold text-slate-300">Sol: {beforeLabel}</span>
        <span className="text-slate-500">A/B Karşılaştırmak için imleci sağa/sola sürükleyin</span>
        <span className="font-semibold text-sky-400">Sağ: {afterLabel}</span>
      </div>

      <div
        ref={containerRef}
        onMouseDown={() => setIsDragging(true)}
        onMouseUp={() => setIsDragging(false)}
        onMouseLeave={() => setIsDragging(false)}
        onMouseMove={handleMouseMove}
        onTouchMove={handleTouchMove}
        className="relative w-full max-w-2xl aspect-[3/4] max-h-[600px] overflow-hidden rounded-lg select-none cursor-ew-resize bg-black/60 border border-slate-800 shadow-2xl"
      >
        {/* After Image (Full width background) */}
        <img
          src={afterImage}
          alt={afterLabel}
          className="absolute inset-0 w-full h-full object-contain pointer-events-none"
        />

        {/* Before Image (Clipped overlay) */}
        <div
          className="absolute inset-0 overflow-hidden pointer-events-none"
          style={{ width: `${sliderPos}%` }}
        >
          <img
            src={beforeImage}
            alt={beforeLabel}
            className="absolute inset-0 w-full h-full object-contain pointer-events-none"
            style={{ width: containerRef.current?.clientWidth || '100%' }}
          />
        </div>

        {/* Divider line and handle */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-sky-400 shadow-lg pointer-events-none"
          style={{ left: `${sliderPos}%` }}
        >
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-sky-500 text-slate-950 flex items-center justify-center shadow-xl border-2 border-white">
            <ChevronsLeftRight className="w-4 h-4" />
          </div>
        </div>

        {/* Floating Badges */}
        <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/70 backdrop-blur text-[11px] font-mono text-slate-200 border border-slate-700 pointer-events-none">
          {beforeLabel}
        </div>
        <div className="absolute top-3 right-3 px-2 py-1 rounded bg-sky-950/80 backdrop-blur text-[11px] font-mono text-sky-300 border border-sky-600/50 pointer-events-none">
          {afterLabel}
        </div>
      </div>
    </div>
  );
};
