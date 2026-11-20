export type Recording = {
  id: string; title: string; source: string; participant_name: string | null;
  scheduled_at: string; ends_at: string; status: string; duration_seconds: number | null;
  error: string | null; processing_notes: string | null; metadata?: Record<string, unknown>;
};
export type Slide = { id: string; time_seconds: number; image_name: string; image_url: string; ocr_text: string; transcript_excerpt: string };
export type Line = { start: number; end: number; text: string };

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const r = await fetch('/api' + url, {
    ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const body = await r.json().catch(() => ({ detail: 'Serverantwort ungültig' }));
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body));
  return body as T;
}

/** Strip the "Error: " prefix String(e) adds. */
export const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export const STATUS: Record<string, { label: string; tone: 'neutral' | 'live' | 'busy' | 'ok' | 'warn' | 'bad' }> = {
  planned: { label: 'Geplant', tone: 'neutral' },
  connecting: { label: 'Tritt bei', tone: 'busy' },
  waiting_room: { label: 'Warteraum', tone: 'warn' },
  recording: { label: 'Nimmt auf', tone: 'live' },
  interrupted: { label: 'Unterbrochen', tone: 'warn' },
  recorded: { label: 'Aufgezeichnet', tone: 'busy' },
  processing: { label: 'Wird verarbeitet', tone: 'busy' },
  ready: { label: 'Fertig', tone: 'ok' },
  error: { label: 'Fehler', tone: 'bad' },
};
export const ACTIVE = ['connecting', 'waiting_room', 'recording', 'processing'];

const tz = { timeZone: 'Europe/Berlin' } as const;
export const day = (v: string) => new Date(v).toLocaleDateString('de-DE', { ...tz, weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });
export const time = (v: string) => new Date(v).toLocaleTimeString('de-DE', { ...tz, hour: '2-digit', minute: '2-digit' });
export const when = (v: string) => `${day(v)}, ${time(v)} Uhr`;
export const dayNum = (v: string) => new Date(v).toLocaleDateString('de-DE', { ...tz, day: '2-digit' });
export const monthShort = (v: string) => new Date(v).toLocaleDateString('de-DE', { ...tz, month: 'short' }).replace('.', '');

export const stamp = (s: number) => {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(sec).padStart(2, '0');
};
/** Human length: "3 Std. 7 Min." / "45 Min." */
export const length = (sec: number) => {
  const m = Math.round(sec / 60), h = Math.floor(m / 60);
  return h ? `${h} Std.${m % 60 ? ' ' + (m % 60) + ' Min.' : ''}` : `${m} Min.`;
};
export const plannedSeconds = (r: Recording) => (new Date(r.ends_at).getTime() - new Date(r.scheduled_at).getTime()) / 1000;
export const recLength = (r: Recording) => length(r.duration_seconds || plannedSeconds(r));
