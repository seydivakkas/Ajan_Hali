import React from 'react';
import { Scale, Package, DollarSign, AlertCircle, CheckCircle2, ShoppingBag } from 'lucide-react';
import { YarnConsumptionItem } from '../types/carpet';

interface YarnRecipeTableProps {
  recipe: YarnConsumptionItem[];
  totalCost: number;
  totalGrossKg: number;
  totalBobbins: number;
  orderQuantity: number;
}

export const YarnRecipeTable: React.FC<YarnRecipeTableProps> = ({
  recipe,
  totalCost,
  totalGrossKg,
  totalBobbins,
  orderQuantity,
}) => {
  const allStockSufficient = recipe.every((item) => item.is_stock_sufficient);

  return (
    <div className="flex flex-col gap-6">
      {/* Metric Summary Widgets */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Gross Kg */}
        <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 flex items-center gap-4">
          <div className="w-11 h-11 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 block">Toplam Brüt İplik (Fireli)</span>
            <span className="text-lg font-bold font-mono text-white">
              {totalGrossKg.toLocaleString('tr-TR', { maximumFractionDigits: 1 })} kg
            </span>
          </div>
        </div>

        {/* Total Bobbins */}
        <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 flex items-center gap-4">
          <div className="w-11 h-11 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <Package className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 block">Tüketim için Bobin Sayısı</span>
            <span className="text-lg font-bold font-mono text-white">
              {totalBobbins} Bobin
            </span>
          </div>
        </div>

        {/* Total Cost */}
        <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 flex items-center gap-4">
          <div className="w-11 h-11 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 block">Toplam İplik Maliyeti</span>
            <span className="text-lg font-bold font-mono text-emerald-400">
              {totalCost.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺
            </span>
          </div>
        </div>

        {/* Stock Status */}
        <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 flex items-center gap-4">
          <div
            className={`w-11 h-11 rounded-lg flex items-center justify-center ${
              allStockSufficient
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                : 'bg-rose-500/10 border border-rose-500/20 text-rose-400'
            }`}
          >
            {allStockSufficient ? (
              <CheckCircle2 className="w-5 h-5" />
            ) : (
              <AlertCircle className="w-5 h-5" />
            )}
          </div>
          <div>
            <span className="text-xs text-slate-400 block">Depo Stok Durumu</span>
            <span
              className={`text-sm font-semibold ${
                allStockSufficient ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {allStockSufficient ? 'Tüm Renkler Hazır' : 'Eksik Stok Var'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-slate-900/80 rounded-xl border border-slate-800 overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShoppingBag className="w-4 h-4 text-sky-400" />
            <h3 className="text-sm font-semibold text-white">
              Renk Bazlı İplik Reçetesi & Satın Alma Dağılımı ({orderQuantity} Adet Halı)
            </h3>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-800/60 text-slate-400 font-semibold border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Kod & İplik Adı</th>
                <th className="py-3 px-4">Materyal / dtex</th>
                <th className="py-3 px-4 text-right">Kaplama</th>
                <th className="py-3 px-4 text-right">Net Kg/Halı</th>
                <th className="py-3 px-4 text-right font-bold text-slate-200">Brüt İhtiyaç</th>
                <th className="py-3 px-4 text-right">Bobin</th>
                <th className="py-3 px-4 text-right">Mevcut Stok</th>
                <th className="py-3 px-4 text-center">Stok Durumu</th>
                <th className="py-3 px-4 text-right">Toplam Tutar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {recipe.map((item) => (
                <tr key={item.yarn_code} className="hover:bg-slate-800/30 transition-colors">
                  {/* Yarn code & Name */}
                  <td className="py-3 px-4">
                    <div className="font-mono font-bold text-sky-400">{item.yarn_code}</div>
                    <div className="text-slate-200 text-[11px]">{item.yarn_name}</div>
                  </td>

                  {/* Material & dtex */}
                  <td className="py-3 px-4">
                    <div className="text-slate-300">{item.material}</div>
                    <div className="text-slate-500 font-mono text-[10px]">{item.dtex} dtex</div>
                  </td>

                  {/* Area % */}
                  <td className="py-3 px-4 text-right font-mono font-semibold">
                    %{item.area_percentage.toFixed(1)}
                  </td>

                  {/* Net Kg per Carpet */}
                  <td className="py-3 px-4 text-right font-mono text-slate-400">
                    {item.yarn_weight_kg_per_carpet.toFixed(2)} kg
                  </td>

                  {/* Gross Weight with Waste */}
                  <td className="py-3 px-4 text-right font-mono font-bold text-white">
                    {item.total_weight_kg_gross_with_waste.toFixed(1)} kg
                  </td>

                  {/* Bobbins */}
                  <td className="py-3 px-4 text-right font-mono">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-sky-300 border border-slate-700">
                      {item.bobbin_count_required}
                    </span>
                  </td>

                  {/* Stock */}
                  <td className="py-3 px-4 text-right font-mono text-slate-400">
                    {item.stock_available_kg.toFixed(0)} kg
                  </td>

                  {/* Status */}
                  <td className="py-3 px-4 text-center">
                    {item.is_stock_sufficient ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" /> Yeterli
                      </span>
                    ) : (
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20">
                          <AlertCircle className="w-3 h-3" /> {item.stock_shortage_kg.toFixed(1)} kg Eksik
                        </span>
                        {item.alternative_yarn_code && (
                          <span className="text-[9px] text-amber-400 font-mono">
                            Öneri: {item.alternative_yarn_code}
                          </span>
                        )}
                      </div>
                    )}
                  </td>

                  {/* Cost */}
                  <td className="py-3 px-4 text-right font-mono font-semibold text-emerald-400">
                    {item.total_cost_tl.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
