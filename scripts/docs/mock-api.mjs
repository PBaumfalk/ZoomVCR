// Beispielinstanz für Handbuch-Screenshots: beantwortet /api/* mit erfundenen Daten
// und reicht alles andere an den Next-Entwicklungsserver weiter.
// Keine echten Veranstaltungen, Referenten oder Teilnehmer.
import http from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const PORT = Number(process.env.PORT || 3100);
const NEXT = Number(process.env.NEXT_PORT || 3101);
const ASSETS = process.env.ASSETS || '';            // Ordner mit video.webm, slide-*.png, snapshot.png
const LOGGED_OUT = process.env.LOGGEDOUT === '1';

const now = Date.now();
const H = 3600e3, D = 24 * H;
const at = (ms) => new Date(ms).toISOString();
// Termine auf volle Viertelstunden runden, damit die Uhrzeiten glaubwürdig aussehen
const q = (ms) => Math.round(ms / (15 * 60e3)) * 15 * 60e3;
// Tag relativ zu heute, feste Uhrzeit (Ortszeit des Rechners, der die Fotos macht)
const dayAt = (days, hour, min = 0) => { const d = new Date(now + days * D); d.setHours(hour, min, 0, 0); return d.getTime(); };
const rec = (id, title, start, minutes, status, extra = {}) => ({
  id, title, source: 'desktop_manual', participant_name: 'ZoomVCR – Aufzeichnung',
  scheduled_at: at(q(start)), ends_at: at(q(start) + minutes * 60e3), status,
  duration_seconds: null, error: null, processing_notes: null, metadata: {}, ...extra,
});

const recordings = [
  rec('a1', 'Fachanwaltsfortbildung Arbeitsrecht – Teil 2', now - 50 * 60e3, 180, 'recording'),
  rec('b2', 'Kündigungsschutz kompakt: Aktuelle Rechtsprechung', dayAt(-2, 9), 180, 'ready', {
    duration_seconds: 2 * 3600 + 41 * 60 + 12,
    processing_notes: '9 Min. Pause und stiller Beginn herausgeschnitten, Original bleibt erhalten',
    metadata: { cut: { status: 'cut', removed_seconds: 1128 } },
  }),
  rec('c3', 'Webinar: Neues im Mutterschutz', dayAt(1, 14), 90, 'planned'),
  rec('d4', 'Verfahrensrecht vor den Arbeitsgerichten', dayAt(6, 9), 240, 'planned'),
  rec('e5', 'Online-Seminar Sozialversicherungsrecht', dayAt(-5, 10), 120, 'error', {
    error: 'Zoom hat den Beitritt nicht bestätigt: Das Meeting wurde vom Host nicht gestartet.',
  }),
  rec('f6', 'Betriebsverfassungsrecht für die Praxis', dayAt(-9, 9), 180, 'ready', { duration_seconds: 2 * 3600 + 55 * 60 }),
  rec('g7', 'Arbeitszeiterfassung nach der Rechtsprechung', dayAt(-12, 14), 120, 'ready', { duration_seconds: 1 * 3600 + 52 * 60 }),
  rec('h8', 'Testaufnahme Probelauf', dayAt(-14, 8, 45), 1, 'ready', {
    source: 'synthetic', participant_name: null, duration_seconds: 59,
    processing_notes: 'Transkription über API fehlgeschlagen: Kein API-Key hinterlegt (Verwaltung → KI und Benachrichtigung) | Kein API-Key hinterlegt; keine KI-Auswertung, keine Daten übertragen',
  }),
];

const slideTexts = [
  ['Kündigungsschutz kompakt', 'Agenda und Überblick'],
  ['Wartezeit und Kleinbetrieb', '§ 1 Abs. 1, § 23 KSchG'],
  ['Verhaltensbedingte Kündigung', 'Abmahnung und Prognoseprinzip'],
  ['Betriebsbedingte Kündigung', 'Sozialauswahl nach § 1 Abs. 3 KSchG'],
  ['Anhörung des Betriebsrats', '§ 102 BetrVG'],
  ['Klagefrist', '§ 4 KSchG – drei Wochen'],
];
const slideAt = [64, 912, 2210, 4105, 6020, 8740];
const slides = slideTexts.map(([t, s], i) => ({
  id: 's' + i, time_seconds: slideAt[i], image_name: `slide-${i}.png`, image_url: `/api/assets/slide-${i}.png`,
  ocr_text: `${t} – ${s}`, transcript_excerpt: '',
}));

// Wie eine echte Testaufnahme: drei Testfolien, kein Transkript ohne KI-Dienst
const testSlides = ['FOLIE 1 - ARBEITSRECHT', 'FOLIE 2 - RECHTSPRECHUNG', 'FOLIE 3 - PRAXISHINWEISE'].map((t, i) => ({
  id: 't' + i, time_seconds: [0, 21, 40.5][i], image_name: `test-${i}.png`, image_url: `/api/assets/test-${i}.png`, ocr_text: t, transcript_excerpt: '',
}));

const transcript = [
  [64, 'Herzlich willkommen zur heutigen Fortbildung. Wir beginnen mit einem Überblick über den allgemeinen Kündigungsschutz.'],
  [118, 'Zunächst zu den Voraussetzungen: Das Arbeitsverhältnis muss länger als sechs Monate bestanden haben.'],
  [175, 'Und der Betrieb muss in der Regel mehr als zehn Arbeitnehmer beschäftigen, § 23 KSchG.'],
  [912, 'Schauen wir uns die Wartezeit genauer an. Unterbrechungen können unter Umständen angerechnet werden.'],
  [1040, 'Bei der Zählung der Arbeitnehmer werden Teilzeitkräfte anteilig berücksichtigt.'],
  [2210, 'Kommen wir zur verhaltensbedingten Kündigung. In aller Regel ist zuvor eine Abmahnung erforderlich.'],
  [2290, 'Die Abmahnung hat eine Hinweis- und eine Warnfunktion. Sie muss das Fehlverhalten konkret bezeichnen.'],
  [2475, 'Entscheidend ist die Prognose: Ist künftig mit weiteren Pflichtverletzungen zu rechnen?'],
  [4105, 'Bei der betriebsbedingten Kündigung steht die unternehmerische Entscheidung am Anfang.'],
  [4230, 'Die Sozialauswahl berücksichtigt Betriebszugehörigkeit, Lebensalter, Unterhaltspflichten und Schwerbehinderung.'],
  [6020, 'Ohne ordnungsgemäße Anhörung des Betriebsrats ist die Kündigung unwirksam, § 102 Abs. 1 Satz 3 BetrVG.'],
  [8740, 'Zum Schluss der Hinweis für die Praxis: Die Klagefrist beträgt drei Wochen ab Zugang der schriftlichen Kündigung.'],
  [8820, 'Vielen Dank für Ihre Aufmerksamkeit. Fragen beantworte ich gern im Anschluss.'],
].map(([start, text], i, all) => ({ start, end: (all[i + 1]?.[0] ?? start + 40) - 1, text }));

const summary = {
  model: 'gpt-5-mini',
  parts: [{
    zusammenfassung: 'Der Vortrag gibt einen Überblick über den allgemeinen Kündigungsschutz: Anwendungsbereich, die drei Kündigungsgründe des § 1 KSchG, die Beteiligung des Betriebsrats und die Klagefrist.',
    gliederung: [
      { titel: 'Anwendungsbereich des KSchG', zeit: '[64s]' },
      { titel: 'Wartezeit und Schwellenwert', zeit: '[912s]' },
      { titel: 'Verhaltensbedingte Kündigung und Abmahnung', zeit: '[2210s]' },
      { titel: 'Betriebsbedingte Kündigung und Sozialauswahl', zeit: '[4105s]' },
      { titel: 'Anhörung des Betriebsrats', zeit: '[6020s]' },
    ],
    argumentation: [
      'Eine Abmahnung ist regelmäßig Voraussetzung der verhaltensbedingten Kündigung, weil erst sie die negative Prognose trägt [2475s].',
      'Die Sozialauswahl ist auf vergleichbare Arbeitnehmer beschränkt; maßgeblich sind die vier Kriterien des § 1 Abs. 3 KSchG [4230s].',
    ],
    praxishinweise: [
      'Klagefrist von drei Wochen ab Zugang sofort notieren [8740s].',
      'Anhörung des Betriebsrats vollständig dokumentieren lassen [6020s].',
    ],
    rechtsquellen: ['§ 1 KSchG', '§ 4 KSchG', '§ 23 KSchG', '§ 102 BetrVG'],
  }],
};

const users = [
  { id: 'u1', username: 'admin', email: 'admin@muster.example', role: 'admin', provider: 'oidc', active: true, mfa_enabled: true, last_login_at: at(now - 20 * 60e3), created_at: at(now - 30 * D) },
  { id: 'u2', username: 'assistenz', email: 'assistenz@muster.example', role: 'recorder', provider: 'oidc', active: true, mfa_enabled: false, last_login_at: at(now - 2 * D), created_at: at(now - 20 * D) },
  { id: 'u3', username: 'fachbereich', email: 'fachbereich@muster.example', role: 'viewer', provider: 'oidc', active: true, mfa_enabled: false, last_login_at: at(now - 4 * D), created_at: at(now - 10 * D) },
  { id: 'u4', username: 'notfall', email: null, role: 'admin', provider: 'local', active: true, mfa_enabled: true, last_login_at: null, created_at: at(now - 30 * D) },
];
const audit = [
  ['admin', 'recording.start', 'recording', 'a1'], ['admin', 'auth.login', 'user', 'u1'],
  ['assistenz', 'recording.create', 'recording', 'c3'], ['assistenz', 'recording.create', 'recording', 'd4'],
  ['fachbereich', 'recording.export', 'recording', 'b2'], ['admin', 'settings.ai_update', 'settings', 'ai'],
  ['admin', 'user.create', 'user', 'u3'], ['admin', 'recording.delete', 'recording', 'x9'],
].map(([actor, action, target_type, target_id], i) => ({
  id: 'a' + i, created_at: at(now - (i * 3 + 1) * H), actor, action, target_type, target_id, ip_address: '10.8.0.' + (12 + i), details: {},
}));

const ai = {
  base_url: 'https://api.openai.com/v1', api_key_set: true, api_key_hint: '…x7Qa', api_key_source: 'ui',
  transcription_provider: 'openai', transcription_model: 'whisper-1', summary_enabled: true, summary_model: 'gpt-5-mini',
  local_asr_available: false, updated: { at: at(now - 8 * D), by: 'admin' },
};
const mail = { configured: true, alert_email: 'it@muster.example', mail_from: 'rekorder@muster.example', smtp_server: 'mail.muster.example:465' };

function routes(method, path) {
  if (path === '/api/auth/config') return { oidc_enabled: true };
  if (LOGGED_OUT && path !== '/api/login') return [401, { detail: 'Login required' }];
  if (path === '/api/me') return { user: users[0] };
  if (path === '/api/desktop/health') return { enabled: true };
  if (path === '/api/recordings') return recordings;
  if (path === '/api/users') return users;
  if (path.startsWith('/api/audit')) return audit;
  if (path === '/api/settings/ai') return ai;
  if (path === '/api/settings/mail') return mail;
  const m = path.match(/^\/api\/recordings\/(\w+)(?:\/(\w+))?$/);
  if (m) {
    const ready = recordings.find((r) => r.id === m[1])?.status === 'ready' && m[1] !== 'h8';
    if (m[2] === 'slides') return m[1] === 'h8' ? testSlides : ready ? slides : [];
    if (m[2] === 'transcript') return ready ? transcript : [];
    if (m[2] === 'summary') return ready ? summary : {};
    if (!m[2]) return recordings.find((r) => r.id === m[1]) || [404, { detail: 'Nicht gefunden' }];
    return { ok: true };
  }
  return [404, { detail: 'Nicht gefunden' }];
}

function sendFile(res, file, type, req) {
  if (!ASSETS || !existsSync(file)) { res.writeHead(404).end(); return; }
  const buf = readFileSync(file);
  const range = req.headers.range?.match(/bytes=(\d+)-(\d*)/);
  if (range) {
    const start = Number(range[1]), end = range[2] ? Number(range[2]) : buf.length - 1;
    res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${buf.length}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1 });
    res.end(buf.subarray(start, end + 1));
  } else {
    res.writeHead(200, { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Length': buf.length }).end(buf);
  }
}

http.createServer((req, res) => {
  const path = req.url.split('?')[0];
  if (path.startsWith('/api/assets/')) return sendFile(res, join(ASSETS, path.slice(12)), 'image/png', req);
  if (path.endsWith('/video')) return sendFile(res, join(ASSETS, path.includes('/h8/') ? 'test.webm' : 'video.webm'), 'video/webm', req);
  if (path === '/api/desktop/snapshot') return sendFile(res, join(ASSETS, 'snapshot.png'), 'image/png', req);
  if (path.startsWith('/api/')) {
    const out = routes(req.method, path);
    const [code, body] = Array.isArray(out) && typeof out[0] === 'number' ? out : [200, out];
    res.writeHead(code, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
    return;
  }
  const up = http.request({ host: '127.0.0.1', port: NEXT, path: req.url, method: req.method, headers: req.headers }, (r) => {
    res.writeHead(r.statusCode, r.headers); r.pipe(res);
  });
  up.on('error', () => res.writeHead(502).end('Next läuft nicht'));
  req.pipe(up);
}).listen(PORT, () => console.log(`Beispielinstanz auf http://localhost:${PORT}${LOGGED_OUT ? ' (abgemeldet)' : ''}`));
