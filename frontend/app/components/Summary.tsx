'use client';
import { Fragment, type ReactNode } from 'react';
import { stamp } from '../lib';

/* The AI analysis comes back as loosely structured JSON (one object per transcript chunk).
   Fields and shapes vary between runs, so everything is rendered generically:
   strings → paragraphs, arrays → lists, objects → labelled entries. Timestamps become links. */

const SECTION: Record<string, string> = {
  zusammenfassung: 'Zusammenfassung', gliederung: 'Gliederung', argumentation: 'Argumentation',
  praxishinweise: 'Praxishinweise', rechtsquellen: 'Rechtsquellen',
};
const ORDER = Object.keys(SECTION);
const label = (k: string) => SECTION[k] || (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, ' ');

// [123.4s] · 123s · 1:02:03 · 01:02:03
const TS = /\[?(\d{1,6}(?:[.,]\d+)?)\s?s\]?(?![a-zäöü])|\b(\d{1,2}):(\d{2}):(\d{2})\b/gi;

function Text({ text, seek }: { text: string; seek: (s: number) => void }) {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(TS)) {
    const sec = m[1] ? parseFloat(m[1].replace(',', '.')) : Number(m[2]) * 3600 + Number(m[3]) * 60 + Number(m[4]);
    out.push(text.slice(last, m.index));
    out.push(<button key={m.index} type="button" className="ts" onClick={() => seek(sec)}>{stamp(sec)}</button>);
    last = (m.index ?? 0) + m[0].length;
  }
  out.push(text.slice(last));
  return <>{out}</>;
}

function Value({ v, seek }: { v: unknown; seek: (s: number) => void }): ReactNode {
  if (v == null || v === '') return null;
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return <p><Text text={String(v)} seek={seek} /></p>;
  if (Array.isArray(v)) {
    if (!v.length) return null;
    return <ul>{v.map((item, i) => <li key={i}>{typeof item === 'object' && item ? <Entry obj={item as Record<string, unknown>} seek={seek} /> : <Text text={String(item)} seek={seek} />}</li>)}</ul>;
  }
  return <Entry obj={v as Record<string, unknown>} seek={seek} block />;
}

/** Object inside a list: first string field is the headline, the rest muted below. */
function Entry({ obj, seek, block }: { obj: Record<string, unknown>; seek: (s: number) => void; block?: boolean }) {
  const entries = Object.entries(obj).filter(([, v]) => v != null && v !== '');
  if (block) return <div className="sum-obj">{entries.map(([k, v]) => <Fragment key={k}><h5>{label(k)}</h5><Value v={v} seek={seek} /></Fragment>)}</div>;
  const [head, ...rest] = entries;
  if (!head) return null;
  return <>
    {typeof head[1] === 'string' ? <strong className="sum-head"><Text text={head[1]} seek={seek} /></strong> : <Value v={head[1]} seek={seek} />}
    {rest.map(([k, v]) => typeof v === 'string'
      ? <span key={k} className="sum-sub"><Text text={v} seek={seek} /></span>
      : <div key={k} className="sum-sub"><Value v={v} seek={seek} /></div>)}
  </>;
}

export function Summary({ data, seek }: { data: Record<string, unknown> | null; seek: (s: number) => void }) {
  if (!data) return <p className="empty-line">Wird geladen …</p>;
  const parts = Array.isArray(data.parts) ? (data.parts as Record<string, unknown>[]) : null;
  if (!parts || !parts.length) {
    return <p className="empty-line">Noch keine KI-Auswertung. Sie entsteht nach der Aufnahme bei der Verarbeitung, wenn unter „KI und Benachrichtigung“ ein Zugang hinterlegt ist.</p>;
  }
  return <div className="summary">
    <p className="hint">Von {String(data.model || 'der KI')} erstellt. Aussagen vor Verwendung am Video prüfen – die Zeitstempel springen an die Stelle.</p>
    {parts.map((part, i) => {
      const keys = [...ORDER.filter(k => k in part), ...Object.keys(part).filter(k => !ORDER.includes(k))];
      return <section key={i} className="sum-part">
        {parts.length > 1 && <div className="sum-part-label">Teil {i + 1} von {parts.length}</div>}
        {keys.map(k => <div key={k} className="sum-section"><h4>{label(k)}</h4><Value v={part[k]} seek={seek} /></div>)}
      </section>;
    })}
  </div>;
}
