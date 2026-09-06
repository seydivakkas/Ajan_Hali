import React, { useState } from 'react';
import { AnalysisPipelineResult } from '../types/carpet';
import { YarnRecipeTable } from './YarnRecipeTable';
export function CurrentQuote({ data }: { data: AnalysisPipelineResult }) {
  const [quote, setQuote] = useState<any>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const calculate = async () => {
    setBusy(true); setError('');
    try {
      const base = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${base}/api/v1/jobs/${encodeURIComponent(data.job_id)}/quote`, { method:'POST' });
      const body = await res.json(); if (!res.ok) throw new Error(body.detail || 'Hesaplama başarısız'); setQuote(body);
    } catch(e: any) { setError(e.message); } finally { setBusy(false); }
  };
  return <section className="mt-6 border border-slate-700 rounded-xl p-4 space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold text-sm">Güncel fiyat ve stokla yeniden hesapla</h3><p className="text-xs text-slate-400 mt-1">Fabrika ayarlarında fiyat / bobin / dtex / stok düzenleyip kaydedin. Bu hesap eski raporu değiştirmez.</p></div><button disabled={busy} onClick={calculate} className="bg-sky-600 rounded-lg p-3 text-xs disabled:opacity-40">{busy ? 'Hesaplanıyor…' : 'Güncel reçeteyi hesapla'}</button></div>
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
    {quote?.source === 'DEMO_SYNTHETIC' && <p className="text-xs text-amber-300">DEMO — Bu hesap sentetik veri içerir; gerçek maliyet teklifi değildir.</p>}
    {quote && <><p role="status" className="text-xs text-sky-300">Yeni hesap · Ayar revizyonu {quote.revision} · {new Date(quote.calculated_at).toLocaleString('tr-TR')} · Aynı desen ve sipariş, güncel iplik değerleri</p><YarnRecipeTable recipe={quote.recipe} totalCost={quote.summary.total_order_cost_tl} totalGrossKg={quote.summary.total_order_yarn_kg} totalBobbins={quote.bobbins} orderQuantity={data.loom_config?.order_quantity || 1} /></>}
  </section>;
}
