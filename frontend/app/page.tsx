'use client';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, CalendarPlus, ChevronDown, ChevronLeft, ChevronRight, Download, FileText, History, Images,
  LayoutDashboard, Library, LogOut, Moon, MonitorPlay, Play, RefreshCw, Search, ShieldCheck, Sparkles, Square,
  Sun, Trash2, Users, X,
} from 'lucide-react';
import { UsersPanel, AuditPanel, ProfilePanel, type Account } from './components/UsersPanel';
import { AISettingsPanel } from './components/AISettingsPanel';
import { Summary } from './components/Summary';
import {
  ACTIVE, STATUS, api, day, dayNum, monthShort, msg, recLength, stamp, time, when,
  type Line, type Recording, type Slide,
} from './lib';

type View = 'dashboard' | 'library' | 'detail' | 'users' | 'audit' | 'profile' | 'ai';
const TITLES: Record<View, string> = {
  dashboard: 'Übersicht', library: 'Mediathek', detail: 'Aufnahme', users: 'Benutzer',
  audit: 'Auditprotokoll', profile: 'Mein Konto', ai: 'KI und Benachrichtigung',
};
const ROLE: Record<string, string> = { admin: 'Administrator', recorder: 'Rekorder', viewer: 'Betrachter' };
const FILTERS = [
  { key: 'all', label: 'Alle', test: () => true },
  { key: 'planned', label: 'Geplant', test: (r: Recording) => r.status === 'planned' },
  { key: 'ready', label: 'Fertig', test: (r: Recording) => r.status === 'ready' },
  { key: 'problem', label: 'Mit Problemen', test: (r: Recording) => ['error', 'interrupted'].includes(r.status) || !!r.error },
] as const;

export default function Home() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [records, setRecords] = useState<Recording[]>([]);
  const [selected, setSelected] = useState<Recording | null>(null);
  const [view, setView] = useState<View>('dashboard');
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [desktopEnabled, setDesktopEnabled] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark' | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api<Recording[]>('/recordings');
      setRecords(list);
      setSelected(old => (old ? list.find(x => x.id === old.id) || null : null));
      setAuthenticated(true);
    } catch (e) {
      if (msg(e).includes('Login required')) setAuthenticated(false); else setError(msg(e));
    }
  }, []);
  useEffect(() => {
    api<{ user: Account }>('/me').then(v => { setAccount(v.user); setAuthenticated(true); refresh(); }).catch(() => setAuthenticated(false));
    try { const t = localStorage.getItem('zoomvcr-theme'); if (t === 'light' || t === 'dark') setTheme(t); } catch { /* storage blocked */ }
  }, [refresh]);
  useEffect(() => {
    if (!authenticated) return;
    api<{ enabled: boolean }>('/desktop/health').then(v => setDesktopEnabled(v.enabled)).catch(() => {});
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [authenticated, refresh]);

  function toggleTheme() {
    const dark = theme ? theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    const next = dark ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('zoomvcr-theme', next); } catch { /* storage blocked */ }
  }
  async function action(id: string, name: string) {
    setBusy(true); setError('');
    try { await api(`/recordings/${id}/${name}`, { method: 'POST' }); await refresh(); } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }
  async function logout() { await api('/logout', { method: 'POST' }).catch(() => {}); setAccount(null); setAuthenticated(false); }
  const go = (v: View) => { setView(v); setSelected(null); setError(''); };
  const choose = (r: Recording) => { setSelected(r); setView('detail'); setError(''); window.scrollTo(0, 0); };

  if (authenticated === null) return <div className="boot">ZoomVCR wird geladen …</div>;
  if (!authenticated) return <Login onDone={a => { setAccount(a); setAuthenticated(true); refresh(); }} />;

  const canRecord = !!account && ['admin', 'recorder'].includes(account.role);
  const live = records.filter(r => ACTIVE.includes(r.status));

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="mark" aria-hidden><i /></span><div><b>ZoomVCR</b><small>Fortbildungsrekorder</small></div></div>
      {canRecord && <button className="btn primary wide" onClick={() => setShowForm(true)}><CalendarPlus size={16} /> Aufnahme planen</button>}
      <nav>
        <NavItem icon={<LayoutDashboard size={17} />} active={view === 'dashboard'} onClick={() => go('dashboard')}>Übersicht</NavItem>
        <NavItem icon={<Library size={17} />} active={view === 'library' || view === 'detail'} onClick={() => go('library')} count={records.length}>Mediathek</NavItem>
        {live.map(r => <button key={r.id} className="nav-live" onClick={() => choose(r)}><span className={'dot ' + STATUS[r.status]?.tone} /><span className="nav-live-text"><b>{STATUS[r.status]?.label}</b>{r.title}</span></button>)}
        {account?.role === 'admin' && <>
          <div className="nav-group">Verwaltung</div>
          <NavItem icon={<Users size={17} />} active={view === 'users'} onClick={() => go('users')}>Benutzer</NavItem>
          <NavItem icon={<History size={17} />} active={view === 'audit'} onClick={() => go('audit')}>Auditprotokoll</NavItem>
          <NavItem icon={<Sparkles size={17} />} active={view === 'ai'} onClick={() => go('ai')}>KI und Benachrichtigung</NavItem>
        </>}
      </nav>
      <div className="sidebar-foot">
        <button className={'account' + (view === 'profile' ? ' active' : '')} onClick={() => go('profile')} title="Mein Konto">
          <span className="avatar">{(account?.username || '?').slice(0, 2).toUpperCase()}</span>
          <span><b>{account?.username}</b><small>{ROLE[account?.role || ''] || ''}</small></span>
        </button>
        <button className="icon-btn" onClick={toggleTheme} title="Hell / Dunkel umschalten" aria-label="Hell / Dunkel umschalten"><Moon size={17} className="only-light" /><Sun size={17} className="only-dark" /></button>
        <button className="icon-btn" onClick={logout} title="Abmelden" aria-label="Abmelden"><LogOut size={17} /></button>
      </div>
    </aside>

    <main className="main">
      {view !== 'detail' && <header className="pagehead">
        <h1>{TITLES[view]}{view === 'library' && <span className="count">{records.length}</span>}</h1>
      </header>}
      {error && <div className="callout bad"><AlertTriangle size={16} /><span>{error}</span><button className="icon-btn sm" onClick={() => setError('')} aria-label="Schließen"><X size={15} /></button></div>}

      {view === 'dashboard' && <Dashboard records={records} choose={choose} canRecord={canRecord} plan={() => setShowForm(true)} />}
      {view === 'library' && <LibraryView records={records} choose={choose} />}
      {view === 'detail' && selected && account && <Detail key={selected.id} rec={selected} account={account} busy={busy} setBusy={setBusy} setError={setError} action={action} refresh={refresh} back={() => go('library')} />}
      {view === 'users' && account?.role === 'admin' && <UsersPanel currentId={account.id} />}
      {view === 'audit' && account?.role === 'admin' && <AuditPanel />}
      {view === 'ai' && account?.role === 'admin' && <AISettingsPanel />}
      {view === 'profile' && account && <ProfilePanel account={account} onChanged={() => api<{ user: Account }>('/me').then(x => setAccount(x.user)).catch(() => { setAuthenticated(false); setAccount(null); })} />}
    </main>

    {showForm && <PlanDialog desktopEnabled={desktopEnabled} close={() => setShowForm(false)} done={async () => { setShowForm(false); go('dashboard'); await refresh(); }} />}
  </div>;
}

function NavItem({ icon, active, onClick, count, children }: { icon: React.ReactNode; active: boolean; onClick: () => void; count?: number; children: React.ReactNode }) {
  return <button className={'nav' + (active ? ' active' : '')} onClick={onClick} aria-current={active ? 'page' : undefined}>{icon}<span>{children}</span>{count != null && <span className="nav-count">{count}</span>}</button>;
}

function Badge({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, tone: 'neutral' };
  return <span className={'badge ' + s.tone}><span className="dot" />{s.label}</span>;
}

function Login({ onDone }: { onDone: (a: Account) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mfa, setMfa] = useState('');
  const [oidc, setOidc] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [local, setLocal] = useState(false);
  useEffect(() => { api<{ oidc_enabled: boolean }>('/auth/config').then(v => setOidc(v.oidc_enabled)).catch(() => {}); }, []);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { const r = await api<{ user: Account }>('/login', { method: 'POST', body: JSON.stringify({ username, password, totp: mfa }) }); onDone(r.user); }
    catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  const showLocal = !oidc || local;
  return <div className="login-wrap">
    <div className="login">
      <div className="brand"><span className="mark" aria-hidden><i /></span><div><b>ZoomVCR</b><small>Fortbildungsrekorder</small></div></div>
      <h1>Anmelden</h1>
      {oidc && <a className="btn primary wide" href="/api/auth/oidc/start"><ShieldCheck size={16} /> Mit SSO anmelden</a>}
      {oidc && !local && <button className="link" onClick={() => setLocal(true)}>Lokales Konto verwenden</button>}
      {showLocal && <form onSubmit={submit} className="form">
        <label className="field"><span>Benutzername</span><input autoFocus={!oidc} autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
        <label className="field"><span>Passwort</span><input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        <label className="field"><span>Authenticator-Code <em>falls eingerichtet</em></span><input inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]*" value={mfa} onChange={e => setMfa(e.target.value)} /></label>
        {error && <div className="callout bad"><AlertTriangle size={16} /><span>{error}</span></div>}
        <button className={'btn wide ' + (oidc ? '' : 'primary')} disabled={busy}>Anmelden</button>
      </form>}
    </div>
  </div>;
}

function RecRow({ r, choose }: { r: Recording; choose: (r: Recording) => void }) {
  return <button className="rec-row" onClick={() => choose(r)}>
    <span className="datebox"><b>{dayNum(r.scheduled_at)}</b><small>{monthShort(r.scheduled_at)}</small></span>
    <span className="rec-main">
      <span className="rec-title">{r.title}</span>
      <span className="rec-meta">{day(r.scheduled_at)} · {time(r.scheduled_at)} Uhr · {recLength(r)}{r.source === 'synthetic' && ' · Testaufnahme'}</span>
    </span>
    <Badge status={r.status} />
    <ChevronRight size={17} className="chev" />
  </button>;
}

function Dashboard({ records, choose, canRecord, plan }: { records: Recording[]; choose: (r: Recording) => void; canRecord: boolean; plan: () => void }) {
  const by = (dir: number) => (a: Recording, b: Recording) => dir * (new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  const live = records.filter(r => ACTIVE.includes(r.status)).sort(by(1));
  const next = records.filter(r => r.status === 'planned').sort(by(1)).slice(0, 5);
  const recent = records.filter(r => !ACTIVE.includes(r.status) && r.status !== 'planned').sort(by(-1)).slice(0, 6);
  if (!records.length) return <div className="empty">
    <MonitorPlay size={28} /><h2>Noch keine Aufnahmen</h2>
    <p>Plane die erste Fortbildung mit Zoom-Link und Uhrzeit. Der Rekorder tritt fünf Minuten vorher bei.</p>
    {canRecord && <button className="btn primary" onClick={plan}><CalendarPlus size={16} /> Aufnahme planen</button>}
  </div>;
  return <div className="stack">
    {live.length > 0 && <section>
      <h2 className="section-title">Läuft gerade</h2>
      <div className="live-grid">{live.map(r => <button key={r.id} className={'live-card ' + STATUS[r.status]?.tone} onClick={() => choose(r)}>
        <Badge status={r.status} />
        <span className="live-title">{r.title}</span>
        <span className="rec-meta">{time(r.scheduled_at)}–{time(r.ends_at)} Uhr{r.error ? ' · ' + r.error : ''}</span>
      </button>)}</div>
    </section>}
    <section>
      <h2 className="section-title">Als Nächstes</h2>
      {next.length ? <div className="list">{next.map(r => <RecRow key={r.id} r={r} choose={choose} />)}</div>
        : <p className="empty-line">Nichts geplant.{canRecord && <> <button className="link" onClick={plan}>Aufnahme planen</button></>}</p>}
    </section>
    {recent.length > 0 && <section>
      <h2 className="section-title">Zuletzt aufgenommen</h2>
      <div className="list">{recent.map(r => <RecRow key={r.id} r={r} choose={choose} />)}</div>
    </section>}
  </div>;
}

function LibraryView({ records, choose }: { records: Recording[]; choose: (r: Recording) => void }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('all');
  const test = FILTERS.find(f => f.key === filter)!.test;
  const visible = records
    .filter(r => r.title.toLowerCase().includes(query.toLowerCase()) && test(r))
    .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime());
  return <div className="stack">
    <div className="toolbar">
      <label className="search"><Search size={16} /><input placeholder="Titel suchen" value={query} onChange={e => setQuery(e.target.value)} /></label>
      <div className="segmented" role="tablist">{FILTERS.map(f => <button key={f.key} role="tab" aria-selected={filter === f.key} className={filter === f.key ? 'on' : ''} onClick={() => setFilter(f.key)}>{f.label}</button>)}</div>
    </div>
    {visible.length ? <div className="list">{visible.map(r => <RecRow key={r.id} r={r} choose={choose} />)}</div>
      : <p className="empty-line">{records.length ? 'Keine Aufnahme passt zur Suche.' : 'Noch keine Aufnahmen.'}</p>}
  </div>;
}

function Detail({ rec, account, busy, setBusy, setError, action, refresh, back }: {
  rec: Recording; account: Account; busy: boolean; setBusy: (b: boolean) => void; setError: (e: string) => void;
  action: (id: string, name: string) => void; refresh: () => Promise<void>; back: () => void;
}) {
  const [slides, setSlides] = useState<Slide[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [tab, setTab] = useState<'summary' | 'transcript'>('summary');
  const [q, setQ] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editName, setEditName] = useState(rec.participant_name || '');
  const player = useRef<HTMLVideoElement>(null);
  const editor = account.role !== 'viewer';
  const zoom = rec.source === 'desktop_manual';
  const joining = ['connecting', 'waiting_room'].includes(rec.status);
  const cut = (rec.metadata?.cut as { status?: string; removed_seconds?: number } | undefined);
  const notes = (rec.processing_notes || '').split(' | ').map(s => s.trim()).filter(Boolean);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<Slide[]>(`/recordings/${rec.id}/slides`), api<Line[]>(`/recordings/${rec.id}/transcript`),
      api<Record<string, unknown>>(`/recordings/${rec.id}/summary`),
    ]).then(([s, t, m]) => { if (!cancelled) { setSlides(s); setLines(t); setSummary(m); } }).catch(() => { if (!cancelled) setSummary({}); });
    return () => { cancelled = true; };
  }, [rec.id, rec.status]);

  const seek = (sec: number) => {
    if (player.current) { player.current.currentTime = sec; player.current.play().catch(() => {}); }
    document.getElementById('recording-player')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  async function remove() {
    setBusy(true); setError('');
    try { await api(`/recordings/${rec.id}`, { method: 'DELETE' }); back(); await refresh(); } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }
  async function saveName(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/recordings/${rec.id}/participant-name`, { method: 'PATCH', body: JSON.stringify({ participant_name: editName }) }); await refresh(); } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  const shownLines = lines.filter(l => l.text.toLowerCase().includes(q.toLowerCase())).slice(0, 800);
  const playable = rec.status === 'ready' || rec.status === 'recorded';
  const exp = (kind: string) => `/api/recordings/${rec.id}/export/${kind}`;

  return <div className="detail">
    <button className="back" onClick={back}><ChevronLeft size={16} /> Mediathek</button>
    <header className="detail-head">
      <div className="detail-title">
        <h1>{rec.title}</h1>
        <div className="detail-meta"><Badge status={rec.status} /><span>{when(rec.scheduled_at)}</span><span>{recLength(rec)}</span><span>{zoom ? 'Zoom' : 'Testaufnahme'}</span>{zoom && rec.participant_name && <span>als „{rec.participant_name}“</span>}</div>
      </div>
      <div className="detail-actions">
        {rec.status === 'planned' && editor && <button className="btn" disabled={busy} onClick={() => action(rec.id, 'start')}><Play size={15} /> Jetzt starten</button>}
        {editor && joining && zoom && <button className="btn" disabled={busy} onClick={() => action(rec.id, 'admit')}><ShieldCheck size={15} /> Beitritt bestätigen</button>}
        {editor && rec.status === 'recording' && <button className="btn" disabled={busy} onClick={() => action(rec.id, 'stop')}><Square size={15} /> Stoppen</button>}
        {editor && ['recorded', 'ready', 'error'].includes(rec.status) && <button className="btn" disabled={busy} onClick={() => action(rec.id, 'process')} title="Schnitt, Folien, Transkript und Auswertung neu erstellen"><RefreshCw size={15} /> Neu verarbeiten</button>}
        {rec.status === 'ready' && <details className="menu">
          <summary className="btn primary"><Download size={15} /> Herunterladen <ChevronDown size={14} /></summary>
          <div className="menu-pop">
            <a href={exp('video')}>Video (MP4)</a>
            {cut?.status === 'cut' && <a href={exp('original')}>Original ungeschnitten</a>}
            <a href={exp('transcript')}>Transkript (TXT)</a>
            <a href={exp('summary')}>Auswertung (JSON)</a>
            <a href={exp('slides')}>Folienindex (JSON)</a>
            <a href={exp('zip')}>Alles als ZIP</a>
          </div>
        </details>}
        {account.role === 'admin' && !ACTIVE.includes(rec.status) && (confirmDelete
          ? <span className="confirm"><button className="btn danger" disabled={busy} onClick={remove}><Trash2 size={15} /> Endgültig löschen</button><button className="btn ghost" onClick={() => setConfirmDelete(false)}>Abbrechen</button></span>
          : <button className="icon-btn" title="Aufnahme löschen" aria-label="Aufnahme löschen" onClick={() => setConfirmDelete(true)}><Trash2 size={17} /></button>)}
      </div>
    </header>

    {rec.error && <div className="callout bad"><AlertTriangle size={16} /><span>{rec.error}</span></div>}
    {notes.length > 0 && <div className="callout"><FileText size={16} /><ul>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>}
    {zoom && joining && <div className="callout warn"><AlertTriangle size={16} /><span>Kann der Rekorder seinen Namen in Zoom nicht selbst prüfen: per VNC nachsehen und danach „Beitritt bestätigen“.</span></div>}

    <div className="detail-grid">
      <div className="detail-left">
        <div className="video" id="recording-player">
          {playable ? <video ref={player} controls preload="metadata" src={`/api/recordings/${rec.id}/video`} />
            : <div className="video-empty"><MonitorPlay size={30} /><span>{rec.status === 'processing' ? 'Video wird verarbeitet' : rec.status === 'planned' ? `Aufnahme beginnt ${when(rec.scheduled_at)}` : ACTIVE.includes(rec.status) ? 'Aufnahme läuft – Video nach dem Ende verfügbar' : 'Kein Video vorhanden'}</span></div>}
        </div>
        {account.role === 'admin' && zoom && ['connecting', 'waiting_room', 'recording'].includes(rec.status) && <figure className="card preview">
          <figcaption>Live-Bild des Rekorders</figcaption>
          <img src={'/api/desktop/snapshot?at=' + Math.floor(Date.now() / 5000)} alt="Bildschirm des Zoom-Rekorders" />
        </figure>}
        {editor && zoom && rec.status === 'planned' && <form className="card inline-form" onSubmit={saveName}>
          <label className="field"><span>Name in Zoom</span><input value={editName} onChange={e => setEditName(e.target.value)} required maxLength={80} /></label>
          <button className="btn" disabled={busy || !editName.trim() || editName === rec.participant_name}>Speichern</button>
        </form>}
        <section>
          <h2 className="section-title"><Images size={16} /> Folien <span className="count">{slides.length}</span></h2>
          {slides.length ? <div className="slides">{slides.map(s => <button className="slide" key={s.id} onClick={() => seek(s.time_seconds)}>
            <img src={s.image_url} alt={`Folie bei ${stamp(s.time_seconds)}`} loading="lazy" />
            <span className="slide-cap"><span className="ts">{stamp(s.time_seconds)}</span><span className="slide-text">{s.ocr_text || s.transcript_excerpt || ''}</span></span>
          </button>)}</div> : <p className="empty-line">Folien erscheinen nach der Verarbeitung.</p>}
        </section>
      </div>
      <aside className="detail-side card">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'summary'} className={tab === 'summary' ? 'on' : ''} onClick={() => setTab('summary')}>Auswertung</button>
          <button role="tab" aria-selected={tab === 'transcript'} className={tab === 'transcript' ? 'on' : ''} onClick={() => setTab('transcript')}>Transkript <span className="count">{lines.length}</span></button>
        </div>
        <div className="side-body">
          {tab === 'summary' && <Summary data={summary} seek={seek} />}
          {tab === 'transcript' && <>
            <label className="search"><Search size={16} /><input placeholder="Im Vortrag suchen" value={q} onChange={e => setQ(e.target.value)} /></label>
            <div className="transcript">{shownLines.map((l, i) => <button key={i} className="tline" onClick={() => seek(l.start)}><span className="ts">{stamp(l.start)}</span><span>{l.text}</span></button>)}</div>
            {!lines.length && <p className="empty-line">Noch kein Transkript.</p>}
            {lines.length > 0 && !shownLines.length && <p className="empty-line">Keine Stelle gefunden.</p>}
          </>}
        </div>
      </aside>
    </div>
  </div>;
}

function PlanDialog({ desktopEnabled, close, done }: { desktopEnabled: boolean; close: () => void; done: () => Promise<void> }) {
  const [title, setTitle] = useState('');
  const [meeting, setMeeting] = useState('');
  const [start, setStart] = useState(() => { const d = new Date(Date.now() + 3600000); d.setMinutes(0, 0, 0); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); });
  const [minutes, setMinutes] = useState(180);
  const [source, setSource] = useState<'synthetic' | 'desktop_manual'>(desktopEnabled ? 'desktop_manual' : 'synthetic');
  const [participantName, setParticipantName] = useState('ZoomVCR – Aufzeichnung');
  const [authorization, setAuthorization] = useState<'host' | 'written_consent' | 'other'>('host');
  const [reference, setReference] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const zoom = source === 'desktop_manual';
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [close]);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api('/recordings', { method: 'POST', body: JSON.stringify({
        title, source, meeting_url: zoom ? meeting : null, participant_name: zoom ? participantName : null,
        scheduled_at: new Date(start).toISOString(), duration_minutes: Number(minutes),
        permission_confirmed: consent, disclosure_acknowledged: consent,
        authorization_basis: zoom ? authorization : null, authorization_reference: zoom ? reference || null : null,
      }) });
      await done();
    } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <div className="modal-layer" onMouseDown={e => { if (e.currentTarget === e.target) close(); }}>
    <form className="modal" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="plan-title">
      <div className="modal-head"><h2 id="plan-title">Aufnahme planen</h2><button type="button" className="icon-btn" onClick={close} aria-label="Schließen"><X size={18} /></button></div>
      <div className="modal-body form">
        <label className="field"><span>Titel</span><input autoFocus value={title} onChange={e => setTitle(e.target.value)} required maxLength={200} placeholder="z. B. Aktuelle Rechtsprechung im Arbeitsrecht" /></label>
        {zoom && <label className="field"><span>Zoom-Link</span><input type="url" value={meeting} onChange={e => setMeeting(e.target.value)} required placeholder="https://us06web.zoom.us/j/…" /></label>}
        <div className="row2">
          <label className="field"><span>Beginn</span><input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} required /></label>
          <label className="field"><span>Dauer in Minuten</span><input type="number" min={1} max={480} value={minutes} onChange={e => setMinutes(Number(e.target.value))} required /></label>
        </div>
        <p className="hint">Der Rekorder tritt 5 Minuten vor Beginn bei und nimmt 15 Minuten über das Ende hinaus auf. Stille am Anfang, am Ende und in Pausen wird danach automatisch herausgeschnitten.</p>
        {zoom && <>
          <label className="field"><span>Name in Zoom</span><input value={participantName} onChange={e => setParticipantName(e.target.value)} required maxLength={80} /></label>
          <div className="row2">
            <label className="field"><span>Berechtigung</span><select value={authorization} onChange={e => setAuthorization(e.target.value as typeof authorization)}>
              <option value="host">Ich bin Veranstalter</option><option value="written_consent">Schriftliche Freigabe</option><option value="other">Sonstige Berechtigung</option>
            </select></label>
            <label className="field"><span>Nachweis <em>{authorization === 'written_consent' ? 'erforderlich' : 'optional'}</em></span><input value={reference} onChange={e => setReference(e.target.value)} maxLength={500} placeholder="z. B. E-Mail vom 05.11.2026" required={authorization === 'written_consent'} /></label>
          </div>
        </>}
        <label className="check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /><span>Die Aufzeichnung ist erlaubt und die Beteiligten sind informiert. Die Angabe wird protokolliert.</span></label>
        <details className="more"><summary>Weitere Optionen</summary>
          <label className="field"><span>Quelle</span><select value={source} onChange={e => setSource(e.target.value as typeof source)}>
            <option value="desktop_manual" disabled={!desktopEnabled}>Zoom-Meeting{desktopEnabled ? '' : ' (auf dem Server nicht aktiviert)'}</option>
            <option value="synthetic">Testaufnahme ohne Zoom (Testbild und Ton)</option>
          </select></label>
        </details>
        {error && <div className="callout bad"><AlertTriangle size={16} /><span>{error}</span></div>}
      </div>
      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={close}>Abbrechen</button>
        <button className="btn primary" disabled={busy || !consent || (zoom && !participantName.trim())}><CalendarPlus size={15} /> Planen</button>
      </div>
    </form>
  </div>;
}
