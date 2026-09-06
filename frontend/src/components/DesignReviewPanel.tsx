import React, { useEffect, useState } from 'react';
import { DesignReview, fetchReviews, saveReview } from '../services/api';
export function DesignReviewPanel({ jobId }: { jobId: string }) {
  const [records, setRecords] = useState<DesignReview[]>([]);
  const [reviewer, setReviewer] = useState('');
  const [note, setNote] = useState('');
  const [decision, setDecision] = useState<DesignReview['decision']>('CHANGES_REQUESTED');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { fetchReviews(jobId).then(setRecords).catch(e => setError(e.message)); }, [jobId]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try { const result = await saveReview(jobId, { reviewer: reviewer.trim(), note: note.trim(), decision }); setRecords([result,...records]); setNote(''); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  return <section className="mt-6 p-5 border border-slate-700 rounded-xl bg-slate-900 space-y-3">
    <h3 className="font-semibold text-sm">Desinatör inceleme kaydı</h3>
    <p className="text-xs text-slate-400">Yerel inceleme günlüğü; isim beyana dayanır. Tasarım kabulü tezgâh uyumluluğunu doğrulamaz veya üretim izni vermez.</p>
    <form onSubmit={submit} className="grid gap-3">
      <label className="text-xs">İnceleyen adı<input required minLength={2} maxLength={100} value={reviewer} onChange={e => setReviewer(e.target.value)} className="block w-full mt-1 p-2 bg-slate-950 rounded border border-slate-700" /></label>
      <label className="text-xs">Karar<select value={decision} onChange={e => setDecision(e.target.value as DesignReview['decision'])} className="block w-full mt-1 p-2 bg-slate-950 rounded border border-slate-700"><option value="CHANGES_REQUESTED">Düzeltme gerekli</option><option value="DESIGN_ACCEPTED">Tasarım kabul edildi</option></select></label>
      <label className="text-xs">İnceleme notu<textarea required minLength={3} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} className="block w-full mt-1 p-2 bg-slate-950 rounded border border-slate-700" /></label>
      <button disabled={busy} className="rounded bg-sky-600 px-3 py-2 text-xs disabled:opacity-50">{busy ? 'Kaydediliyor…' : 'İncelemeyi kaydet'}</button>
    </form>
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
    <div aria-live="polite" className="space-y-2">{records.map(r => <article key={r.id} className="border-t border-slate-700 pt-3 text-xs"><p className="text-sky-300">{r.decision === 'DESIGN_ACCEPTED' ? 'Tasarım kabul edildi' : 'Düzeltme gerekli'} · {r.reviewer} · {new Date(r.created_at).toLocaleString('tr-TR')}</p><p className="mt-1 whitespace-pre-wrap">{r.note}</p><p className="text-slate-500 mt-1">Rapor izi: {r.report_sha256.slice(0,16)}</p></article>)}</div>
  </section>;
}
