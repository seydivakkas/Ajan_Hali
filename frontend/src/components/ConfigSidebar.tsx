import React, { useState, useRef, useEffect } from 'react';
import {
  Upload,
  Settings,
  Sliders,
  Sparkles,
  Maximize2,
  RefreshCw,
  Image as ImageIcon,
  Check,
  Cpu,
  Sun
} from 'lucide-react';
import { PhotoEditor } from './PhotoEditor';
import { LoomFormConfig } from '../types/carpet';

interface ConfigSidebarProps {
  config: LoomFormConfig;
  onChangeConfig: (newConfig: LoomFormConfig) => void;
  onAnalyze: (file: File) => void;
  isLoading: boolean;
  canAnalyze?: boolean;
}

export const ConfigSidebar: React.FC<ConfigSidebarProps> = ({
  config,
  onChangeConfig,
  onAnalyze,
  isLoading,
  canAnalyze = true,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (file: File) => {
    if (isLoading) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 20 * 1024 * 1024) {
      setFileError("JPG / PNG formatında, en fazla 20 MB fotoğraf seçin.");
      return;
    }
    setFileError(null);
    onChangeConfig({ ...config, manual_corners: undefined, repair_regions: [] });
    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (field: keyof LoomFormConfig, val: any) => {
    onChangeConfig({
      ...config,
      [field]: val,
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    if (config.manual_corners && config.manual_corners.length !== 4) { setFileError("Dört köşeyi tamamlayın veya seçimleri temizleyin."); return; }
    if (!Number.isFinite(config.max_colors)) { setFileError("Renk kapasitesini seçin."); return; }
    onAnalyze(selectedFile);
  };

  return (
    <div className="w-full lg:w-84 xl:w-96 bg-industrial-900 border-r border-slate-800 p-5 flex flex-col gap-6 overflow-y-auto shrink-0">
      <div>
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
          <Settings className="w-4 h-4 text-sky-400" />
          Tezgâh & Üretim Parametreleri
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Fotoğrafı yükleyin ve üretim tezgâhının mekanik kısıtlarını girin.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        {/* File Dropzone */}
        <div>
          <label className="text-xs font-medium text-slate-300 block mb-2">
            Rakip Halı Fotoğrafı (JPG / PNG)
          </label>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-all ${
              dragOver
                ? 'border-sky-400 bg-sky-500/10'
                : selectedFile
                ? 'border-emerald-500/50 bg-emerald-500/5'
                : 'border-slate-700 hover:border-slate-600 bg-slate-800/40'
            }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              accept="image/jpeg,image/png"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileSelect(e.target.files[0]);
                }
              }}
            />

            {previewUrl ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-24 h-28 rounded border border-slate-700 overflow-hidden relative shadow-md bg-black">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                    <span className="text-[10px] text-white">Değiştir</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                  <Check className="w-3.5 h-3.5" />
                  <span className="truncate max-w-[200px]">{selectedFile?.name}</span>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-2">
                <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-slate-400">
                  <Upload className="w-5 h-5 text-sky-400" />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-200">
                    Fotoğrafı sürükleyin veya tıklayın
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Mağaza/saha çekimi veya taranmış görsel
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {previewUrl && <PhotoEditor key={previewUrl} src={previewUrl} config={config} onChange={onChangeConfig} disabled={isLoading} />}

        {/* Carpet Dimensions */}
        <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-3.5 flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
            <Maximize2 className="w-3.5 h-3.5 text-sky-400" />
            Halı Ebatları (cm)
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">En (Genişlik)</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  value={Number.isFinite(config.width_cm) ? config.width_cm : ""}
                  onChange={(e) => handleInputChange('width_cm', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2.5 top-1.5 text-[10px] text-slate-500">cm</span>
              </div>
            </div>
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Boy (Uzunluk)</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  value={Number.isFinite(config.length_cm) ? config.length_cm : ""}
                  onChange={(e) => handleInputChange('length_cm', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2.5 top-1.5 text-[10px] text-slate-500">cm</span>
              </div>
            </div>
          </div>
        </div>

        {/* Loom Mechanics */}
        <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-3.5 flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
            <Sliders className="w-3.5 h-3.5 text-sky-400" />
            Tezgâh & Jakar Yapılandırması
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-[11px] text-slate-400 block mb-1" title="Reed Density">Tarak Sıklığı</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  value={Number.isFinite(config.reed_density) ? config.reed_density : ""}
                  onChange={(e) => handleInputChange('reed_density', parseInt(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2 top-1.5 text-[9px] text-slate-500">tel/m</span>
              </div>
            </div>
            <div>
              <span className="text-[11px] text-slate-400 block mb-1" title="Pick Density">Atkı Sıklığı</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  value={Number.isFinite(config.pick_density) ? config.pick_density : ""}
                  onChange={(e) => handleInputChange('pick_density', parseInt(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2 top-1.5 text-[9px] text-slate-500">vuruş/m</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Hav Yüksekliği</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  step="0.5"
                  value={Number.isFinite(config.pile_height_mm) ? config.pile_height_mm : ""}
                  onChange={(e) => handleInputChange('pile_height_mm', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2.5 top-1.5 text-[10px] text-slate-500">mm</span>
              </div>
            </div>
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Maks. Renk</span>
              <select
                value={Number.isFinite(config.max_colors) ? config.max_colors : ""}
                onChange={(e) => handleInputChange('max_colors', parseInt(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              >
                <option value="">Renk kapasitesi seçin</option>
                <option value={1}>1 Renk</option>
                <option value={2}>2 Renk</option>
                <option value={4}>4 Renk</option>
                <option value={6}>6 Renk</option>
                <option value={8}>8 Renk (Standart)</option>
                <option value={10}>10 Renk</option>
                <option value={12}>12 Renk (Geniş Cağlık)</option>
                <option value={16}>16 Renk (Çift Cağlık)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Sipariş Adedi</span>
              <input
                type="number"
                  required
                value={Number.isFinite(config.order_quantity) ? config.order_quantity : ""}
                onChange={(e) => handleInputChange('order_quantity', parseInt(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Fire / Zayiat (%)</span>
              <div className="relative">
                <input
                  type="number"
                  required
                  step="1"
                  value={Number.isFinite(config.waste_coefficient) ? config.waste_coefficient * 100 : ""}
                  onChange={(e) => handleInputChange('waste_coefficient', (parseFloat(e.target.value)) / 100)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
                />
                <span className="absolute right-2.5 top-1.5 text-[10px] text-slate-500">%</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {(['weave_structure_factor', 'anchor_length_mm'] as const).map((field,i) => <label className="text-xs text-slate-400" key={field}>
              {i === 0 ? 'Dokuma uzama faktörü' : 'Düğüm altı payı (mm)'}
              <input required type="number" min={i===0 ? .01 : 0} step="any" value={Number.isFinite(config[field]) ? config[field] : ''} onChange={e => handleInputChange(field, parseFloat(e.target.value))} className="w-full mt-1 p-2 rounded bg-slate-950 border border-slate-700" />
            </label>)}
          </div>
          {/* AI Symmetry Switch */}
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs text-slate-300">AI Simetri Onarımı</span>
            </div>
            <input
              type="checkbox"
              checked={config.enable_symmetry}
              onChange={(e) => handleInputChange('enable_symmetry', e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900 bg-slate-900 cursor-pointer"
            />
          </div>

          {/* Inpainting Mode Selector */}
          <div className="pt-1">
            <span className="text-[11px] text-slate-400 block mb-1">Onarım / Tamamlama Yöntemi</span>
            <select
              value={config.symmetry_mode}
              onChange={(e) => handleInputChange('symmetry_mode', e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
            >
              <option value="QUADRANT_4FOLD">Klasik 4-Kadran Dihedral Simetri</option>
              <option value="ABSTRACT_GENERATIVE">Modern / Asimetrik Üretken AI (Faz 2)</option>
              <option value="HORIZONTAL">Yatay Ayna Yansıması</option>
              <option value="VERTICAL">Dikey Ayna Yansıması</option>
            </select>
          </div>

          {/* FastSAM AI Switch */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-sky-400" />
              <div>
                <span className="text-xs text-slate-300 block">FastSAM AI İzolasyonu</span>
                <span className="text-[10px] text-sky-400 font-mono">CUDA Destekli Sıfır-Shot</span>
              </div>
            </div>
            <input
              type="checkbox"
              checked={config.enable_sam}
              onChange={(e) => handleInputChange('enable_sam', e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900 bg-slate-900 cursor-pointer"
            />
          </div>

          {/* Dereflection Switch */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <div className="flex items-center gap-2">
              <Sun className="w-3.5 h-3.5 text-amber-300" />
              <div>
                <span className="text-xs text-slate-300 block">Flaş & Parlama Giderme</span>
                <span className="text-[10px] text-slate-400 font-mono">Dichromatic Dereflection</span>
              </div>
            </div>
            <input
              type="checkbox"
              checked={config.enable_dereflection}
              onChange={(e) => handleInputChange('enable_dereflection', e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900 bg-slate-900 cursor-pointer"
            />
          </div>
        </div>

        <div className="rounded-lg border border-slate-700 p-3 text-xs text-slate-300" aria-live="polite">
          {Number.isFinite(config.width_cm * config.length_cm * config.reed_density * config.pick_density * config.order_quantity) ? <>Matris önizlemesi: {Math.round(config.width_cm / 100 * config.reed_density).toLocaleString('tr-TR')} × {Math.round(config.length_cm / 100 * config.pick_density).toLocaleString('tr-TR')} hücre
          <p className="mt-1 text-slate-400">{(config.width_cm * config.length_cm / 10000 * config.order_quantity).toLocaleString('tr-TR')} m² sipariş alanı</p></> : "Matris ve sipariş alanını hesaplamak için parametreleri girin."}
        </div>
        {fileError && <p role="alert" className="text-xs text-rose-300">{fileError}</p>}
        {!canAnalyze && <p className="text-xs text-amber-300">Analiz için Fabrika Ayarları bölümünde şirket adını ve iplik bilgilerini kaydedin.</p>}
        {/* Submit Button */}
        <button
          type="submit"
          disabled={!selectedFile || isLoading || !canAnalyze}
          className="w-full py-3 px-4 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-sky-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {isLoading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin text-slate-950" />
              <span>CIEDE2000 & CAD İşleniyor...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 text-slate-950" />
              <span>Halıyı Analiz Et & CAD Üret</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
};
