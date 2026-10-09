import { useEffect, useState, type FormEvent } from 'react';
import { App } from './App';
import { fetchSession, login, logout, type SessionInfo } from './services/auth';

export function AuthGate() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchSession().then(setSession).catch(() => setSession(null)).finally(() => setLoading(false));
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      setSession(await login(username, password));
      setPassword('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Oturum açılamadı.');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="min-h-screen flex items-center justify-center text-slate-700">Bağlantı kontrol ediliyor…</div>;

  if (session) return <>
    {session.mode !== 'local' && <div className="flex justify-end items-center gap-4 px-5 py-2 bg-slate-900 text-white text-xs">
      <span>{session.workspace_id ? `${session.workspace_id} · ` : ''}{session.username} · {session.role}</span>
      <button type="button" className="underline" onClick={async () => {
        try { await logout(); setSession(null); } catch { setError('Çıkış yapılamadı.'); }
      }}>Çıkış yap</button>
    </div>}
    <App />
  </>;

  return <main className="min-h-screen flex items-center justify-center bg-slate-100 px-4">
    <form onSubmit={submit} className="w-full max-w-sm bg-white p-8 rounded-xl shadow space-y-4">
      <h1 className="text-2xl font-semibold">Ajan Halı · Oturum aç</h1>
      <p className="text-sm text-slate-600">Yetkilendirilmiş yerel kullanıcı hesabınızla giriş yapın.</p>
      <label className="block text-sm">Kullanıcı adı
        <input required autoComplete="username" className="mt-1 w-full border rounded-md p-2"
          value={username} onChange={e => setUsername(e.target.value)} />
      </label>
      <label className="block text-sm">Parola
        <input required type="password" autoComplete="current-password" className="mt-1 w-full border rounded-md p-2"
          value={password} onChange={e => setPassword(e.target.value)} />
      </label>
      {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
      <button disabled={submitting} className="w-full bg-slate-900 text-white rounded-md p-2 disabled:opacity-50">
        {submitting ? 'Doğrulanıyor…' : 'Giriş yap'}
      </button>
    </form>
  </main>;
}
