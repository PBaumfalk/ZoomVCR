'use client';
import {FormEvent, useCallback, useEffect, useState} from 'react';
import {AlertTriangle, KeyRound, Mail, PlugZap, Trash2} from 'lucide-react';
import {api, msg} from '../lib';

type AISettings = {
  base_url:string; api_key_set:boolean; api_key_hint:string; api_key_source:'ui'|'env'|'none';
  transcription_provider:'openai'|'local'|'off'; transcription_model:string;
  summary_enabled:boolean; summary_model:string; local_asr_available:boolean;
  updated:{at:string;by:string}|null;
};
type MailSettings = {configured:boolean;alert_email:string;mail_from:string;smtp_server:string};
type TestResult = {ok:boolean;detail:string;transcription_model_available?:boolean;summary_model_available?:boolean};


const TRANSCRIPTION_MODELS=['gpt-4o-transcribe','gpt-4o-mini-transcribe','whisper-1'];

export function AISettingsPanel(){
  const [cfg,setCfg]=useState<AISettings|null>(null);
  const [key,setKey]=useState('');
  const [baseUrl,setBaseUrl]=useState('');
  const [provider,setProvider]=useState<AISettings['transcription_provider']>('openai');
  const [tModel,setTModel]=useState('');
  const [sEnabled,setSEnabled]=useState(true);
  const [sModel,setSModel]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
  const [test,setTest]=useState<TestResult|null>(null);
  const [mail,setMail]=useState<MailSettings|null>(null);const [mailResult,setMailResult]=useState<TestResult|null>(null);

  const apply=(c:AISettings)=>{setCfg(c);setBaseUrl(c.base_url);setProvider(c.transcription_provider);setTModel(c.transcription_model);setSEnabled(c.summary_enabled);setSModel(c.summary_model)};
  const load=useCallback(async()=>{try{apply(await api<AISettings>('/settings/ai'))}catch(e){setError(msg(e))}},[]);
  useEffect(()=>{load();api<MailSettings>('/settings/mail').then(setMail).catch(()=>{})},[load]);
  async function mailTest(){setBusy(true);setMailResult(null);try{setMailResult(await api<TestResult>('/settings/mail/test',{method:'POST'}))}catch(e){setMailResult({ok:false,detail:msg(e)})}finally{setBusy(false)}}

  async function save(e:FormEvent){e.preventDefault();setBusy(true);setError('');setNotice('');setTest(null);try{
    const payload:Record<string,unknown>={base_url:baseUrl,transcription_provider:provider,transcription_model:tModel,summary_enabled:sEnabled,summary_model:sModel};
    if(key.trim())payload.api_key=key.trim();
    const endpointChanged=cfg&&baseUrl.replace(/\/+$/,'')!==cfg.base_url;
    const next=await api<AISettings>('/settings/ai',{method:'PUT',body:JSON.stringify(payload)});
    apply(next);setKey('');
    setNotice(endpointChanged&&!payload.api_key&&!next.api_key_set?'Gespeichert. Der API-Key wurde wegen der geänderten Adresse entfernt – bitte neu eintragen.':'Einstellungen gespeichert.');
  }catch(e){setError(msg(e))}finally{setBusy(false)}}

  async function removeKey(){setBusy(true);setError('');setNotice('');setTest(null);try{apply(await api<AISettings>('/settings/ai',{method:'PUT',body:JSON.stringify({clear_api_key:true})}));setNotice('API-Key entfernt.')}catch(e){setError(msg(e))}finally{setBusy(false)}}

  async function runTest(){setBusy(true);setError('');setTest(null);try{setTest(await api<TestResult>('/settings/ai/test',{method:'POST'}))}catch(e){setError(msg(e))}finally{setBusy(false)}}

  if(!cfg)return <div className="stack narrow">{error?<div className="callout bad"><AlertTriangle size={16}/><span>{error}</span></div>:<p className="empty-line">Lade Einstellungen …</p>}</div>;
  const keyState=cfg.api_key_set?(cfg.api_key_source==='env'?`aus der Server-Konfiguration (${cfg.api_key_hint})`:`hinterlegt (${cfg.api_key_hint})`):'nicht hinterlegt';
  return <div className="stack narrow">
    {error&&<div className="callout bad"><AlertTriangle size={16}/><span>{error}</span></div>}{notice&&<div className="callout ok"><span>{notice}</span></div>}
    <form className="card" onSubmit={save}>
      <div className="card-head"><h2><KeyRound size={17}/> KI-Dienst</h2><span className={'badge '+(cfg.api_key_set?'ok':'warn')}><span className="dot"/>{cfg.api_key_set?'Zugang hinterlegt':'Kein Zugang'}</span></div>
      <div className="form">
        <label className="field"><span>API-Key <em>{cfg.api_key_set?`${keyState} – leer lassen, um ihn zu behalten`:'wird verschlüsselt gespeichert und nie wieder angezeigt'}</em></span><input type="password" autoComplete="off" spellCheck={false} value={key} onChange={e=>setKey(e.target.value)} placeholder={cfg.api_key_set?'••••••••••••':'sk-…'}/></label>
        <label className="field"><span>Adresse <em>OpenAI-kompatibel</em></span><input value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} required pattern="https://.+" spellCheck={false}/></label>
        <h3 className="form-sub">Transkription</h3>
        <div className="row2">
          <label className="field"><span>Verfahren</span><select value={provider} onChange={e=>setProvider(e.target.value as AISettings['transcription_provider'])}>
            <option value="openai">Über den KI-Dienst</option>
            <option value="local" disabled={!cfg.local_asr_available}>Lokal mit Whisper{cfg.local_asr_available?'':' (nicht installiert)'}</option>
            <option value="off">Aus</option>
          </select></label>
          {provider==='openai'&&<label className="field"><span>Modell</span><input list="zoomvcr-transcription-models" value={tModel} onChange={e=>setTModel(e.target.value)} required spellCheck={false}/><datalist id="zoomvcr-transcription-models">{TRANSCRIPTION_MODELS.map(m=><option key={m} value={m}/>)}</datalist></label>}
        </div>
        {provider==='openai'&&<p className="hint">Empfohlen ist gpt-4o-transcribe. whisper-1 erfindet bei Stille Text. Stille Abschnitte werden ohnehin nicht übertragen.</p>}
        <h3 className="form-sub">Auswertung</h3>
        <label className="check"><input type="checkbox" checked={sEnabled} onChange={e=>setSEnabled(e.target.checked)}/><span>Zusammenfassung, Gliederung und Rechtsquellen per KI erstellen</span></label>
        {sEnabled&&<label className="field"><span>Modell</span><input value={sModel} onChange={e=>setSModel(e.target.value)} required spellCheck={false}/></label>}
        <p className="hint">Ton und Transkript gehen an den KI-Dienst. Die Freigabe der Veranstaltung muss das abdecken.</p>
        <div className="actions">
          <button className="btn primary" disabled={busy}>Speichern</button>
          <button type="button" className="btn" disabled={busy||!cfg.api_key_set} onClick={runTest}><PlugZap size={15}/> Verbindung testen</button>
          {cfg.api_key_set&&cfg.api_key_source==='ui'&&<button type="button" className="btn ghost" disabled={busy} onClick={removeKey}><Trash2 size={15}/> Key entfernen</button>}
        </div>
        {test&&<div className={'callout '+(test.ok?'ok':'bad')}><span>{test.detail}
          {test.ok&&test.transcription_model_available===false&&provider==='openai'&&<> · Transkriptionsmodell „{cfg.transcription_model}“ nicht in der Modellliste</>}
          {test.ok&&test.summary_model_available===false&&sEnabled&&<> · Auswertungsmodell „{cfg.summary_model}“ nicht in der Modellliste</>}</span>
        </div>}
        {cfg.updated&&<p className="hint">Zuletzt geändert am {new Date(cfg.updated.at).toLocaleString('de-DE',{timeZone:'Europe/Berlin',dateStyle:'medium',timeStyle:'short'})} von {cfg.updated.by}.</p>}
      </div>
    </form>
    {mail&&<section className="card">
      <div className="card-head"><h2><Mail size={17}/> Benachrichtigung bei Problemen</h2><span className={'badge '+(mail.configured?'ok':'warn')}><span className="dot"/>{mail.configured?'Eingerichtet':'Nicht eingerichtet'}</span></div>
      <div className="form">
        <p className="hint">Eine E-Mail geht hinaus, wenn eine Aufnahme scheitert, Zoom länger als zwei Minuten keinen Ton hat, die Verarbeitung scheitert oder eine Aufnahme fast stumm ist. Je Aufnahme und Anlass kommt höchstens eine Mail.</p>
        {mail.configured?<dl className="facts"><dt>Empfänger</dt><dd>{mail.alert_email}</dd><dt>Absender</dt><dd>{mail.mail_from||'Postfach'}</dd><dt>Server</dt><dd>{mail.smtp_server}</dd></dl>
          :<p className="hint">Empfänger und Mailserver stehen in der <code>.env</code> auf dem Server (<code>ZOOMVCR_ALERT_EMAIL</code>, <code>ZOOMVCR_SMTP_URL</code>, <code>ZOOMVCR_MAIL_FROM</code>).</p>}
        <div className="actions"><button type="button" className="btn" disabled={busy||!mail.configured} onClick={mailTest}><Mail size={15}/> Testmail senden</button></div>
        {mailResult&&<div className={'callout '+(mailResult.ok?'ok':'bad')}><span>{mailResult.detail}</span></div>}
      </div>
    </section>}
  </div>;
}
