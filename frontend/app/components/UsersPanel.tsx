'use client';
import {FormEvent, useCallback, useEffect, useState} from 'react';
import {AlertTriangle, KeyRound, Shield, ShieldCheck, UserPlus} from 'lucide-react';
import {api, msg} from '../lib';

export type Account = {id:string;username:string;email:string|null;role:'admin'|'recorder'|'viewer';provider:'local'|'oidc';active:boolean;mfa_enabled:boolean;last_login_at:string|null;created_at:string};
type AuditRow = {id:string;created_at:string;actor:string;action:string;target_type:string;target_id:string;ip_address:string|null;details:Record<string,unknown>};
const roleLabel:Record<string,string>={admin:'Administrator',recorder:'Rekorder',viewer:'Betrachter'};
export function UsersPanel({currentId}:{currentId:string}){
 const [users,setUsers]=useState<Account[]>([]); const [error,setError]=useState('');const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
 const [resetId,setResetId]=useState<string|null>(null);const [resetPassword,setResetPassword]=useState('');
 const [name,setName]=useState('');const [email,setEmail]=useState('');const [role,setRole]=useState<Account['role']>('viewer');const [provider,setProvider]=useState<'local'|'oidc'>('oidc');const [password,setPassword]=useState('');
 const load=useCallback(async()=>{try{setUsers(await api<Account[]>('/users'));}catch(e){setError(msg(e))}},[]);
 useEffect(()=>{load()},[load]);
 async function create(e:FormEvent){e.preventDefault();setBusy(true);setError('');setMessage('');try{
   await api('/users',{method:'POST',body:JSON.stringify({username:name,email:email||null,role,provider,password:provider==='local'?password:null})});
   setMessage('Benutzer wurde angelegt.');setName('');setEmail('');setPassword('');setRole('viewer');setProvider('oidc');await load();
 }catch(e){setError(msg(e))}finally{setBusy(false)}}
 async function update(user:Account,change:{role?:Account['role'];active?:boolean}){
   setBusy(true);setError('');setMessage('');try{await api(`/users/${user.id}`,{method:'PATCH',body:JSON.stringify(change)});setMessage('Änderung gespeichert. Bestehende Sitzungen wurden widerrufen.');await load()}catch(e){setError(msg(e))}finally{setBusy(false)}
 }
 async function reset(user:Account){setBusy(true);setError('');try{await api(`/users/${user.id}/reset-password`,{method:'POST',body:JSON.stringify({new_password:resetPassword})});setMessage('Passwort geändert, bisherige Sitzungen und MFA widerrufen.');setResetId(null);setResetPassword('')}catch(e){setError(msg(e))}finally{setBusy(false)} }
 return <div className="stack narrow">
   {error&&<div className="callout bad"><AlertTriangle size={16}/><span>{error}</span></div>}{message&&<div className="callout ok"><span>{message}</span></div>}
   <section className="card">
     <div className="card-head"><h2>Konten</h2><span className="count">{users.length}</span></div>
     <div className="table-scroll"><table className="table"><thead><tr><th>Benutzer</th><th>Rolle</th><th>Anmeldung</th><th>Status</th><th/></tr></thead><tbody>
       {users.map(u=><tr key={u.id}><td><b>{u.username}</b><div className="muted">{u.email||'keine E-Mail'}</div></td>
         <td><select className="compact" aria-label={`Rolle von ${u.username}`} value={u.role} disabled={busy||u.id===currentId} onChange={e=>update(u,{role:e.target.value as Account['role']})}><option value="viewer">Betrachter</option><option value="recorder">Rekorder</option><option value="admin">Administrator</option></select></td>
         <td>{u.provider==='oidc'?'Kanzlei-Login':'Passwort'}{u.mfa_enabled&&<div className="muted"><Shield size={12}/> 2FA aktiv</div>}</td>
         <td><span className={'badge '+(u.active?'ok':'bad')}><span className="dot"/>{u.active?'Aktiv':'Gesperrt'}</span></td>
         <td className="cell-actions"><button className="btn sm ghost" disabled={busy||u.id===currentId} onClick={()=>update(u,{active:!u.active})}>{u.active?'Sperren':'Entsperren'}</button>{u.provider==='local'&&<button className="btn sm ghost" disabled={busy} onClick={()=>{setResetId(u.id);setResetPassword('')}} title="Neues Passwort vergeben und Sitzungen widerrufen"><KeyRound size={14}/> Passwort</button>}
         {resetId===u.id&&<form className="inline-form" onSubmit={e=>{e.preventDefault();reset(u)}}><input type="password" aria-label="Neues Passwort" placeholder="Neues Passwort (ab 14 Zeichen)" autoComplete="new-password" minLength={14} maxLength={256} value={resetPassword} onChange={e=>setResetPassword(e.target.value)} required/><button className="btn sm primary" disabled={busy||resetPassword.length<14}>Setzen</button><button className="btn sm ghost" type="button" onClick={()=>setResetId(null)}>Abbrechen</button></form>}</td>
       </tr>)}
     </tbody></table></div>
     <p className="hint">Betrachter sehen die Mediathek, dürfen aber nichts planen oder ändern. Änderungen an Rolle oder Sperre beenden laufende Sitzungen sofort.</p>
   </section>
   <section className="card">
     <div className="card-head"><h2><UserPlus size={17}/> Konto hinzufügen</h2></div>
     <form className="form" onSubmit={create}>
       <div className="row2"><label className="field"><span>Benutzername</span><input value={name} onChange={e=>setName(e.target.value)} minLength={3} maxLength={64} pattern="[A-Za-z0-9._-]+" required placeholder="vorname.nachname" /></label><label className="field"><span>E-Mail-Adresse {provider==='oidc'?'':<em>optional</em>}</span><input type="email" value={email} onChange={e=>setEmail(e.target.value)} required={provider==='oidc'} /></label></div>
       <div className="row2"><label className="field"><span>Rolle</span><select value={role} onChange={e=>setRole(e.target.value as Account['role'])}><option value="viewer">Betrachter</option><option value="recorder">Rekorder</option><option value="admin">Administrator</option></select></label><label className="field"><span>Anmeldung</span><select value={provider} onChange={e=>setProvider(e.target.value as 'local'|'oidc')}><option value="oidc">Kanzlei-Login (OIDC)</option><option value="local">Lokales Passwort</option></select></label></div>
       {provider==='local'?<label className="field"><span>Startpasswort <em>mindestens 14 Zeichen</em></span><input type="password" value={password} minLength={14} maxLength={256} onChange={e=>setPassword(e.target.value)} required autoComplete="new-password"/></label>:<p className="hint">Beim ersten Kanzlei-Login wird die bestätigte E-Mail-Adresse mit diesem Konto verknüpft.</p>}
       <div><button className="btn primary" type="submit" disabled={busy}><UserPlus size={15}/> Konto anlegen</button></div>
     </form>
   </section>
 </div>
}
export function AuditPanel(){const [rows,setRows]=useState<AuditRow[]>([]);const [error,setError]=useState('');const [offset,setOffset]=useState(0);
 useEffect(()=>{api<AuditRow[]>(`/audit?offset=${offset}&limit=100`).then(setRows).catch(e=>setError(msg(e)))},[offset]);
 return <div className="stack">{error&&<div className="callout bad"><AlertTriangle size={16}/><span>{error}</span></div>}<section className="card flush"><div className="table-scroll"><table className="table"><thead><tr><th>Zeitpunkt</th><th>Wer</th><th>Ereignis</th><th>Betrifft</th></tr></thead><tbody>{rows.map(e=><tr key={e.id}><td className="nowrap">{new Date(e.created_at).toLocaleString('de-DE',{timeZone:'Europe/Berlin',dateStyle:'short',timeStyle:'medium'})}</td><td>{e.actor}</td><td><code>{e.action}</code></td><td className="muted">{e.target_type} <code>{e.target_id.slice(0,8)}</code></td></tr>)}</tbody></table></div>{!rows.length&&<p className="empty-line pad">Noch keine Einträge.</p>}</section><div className="pager"><button className="btn sm" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-100))}>Neuere</button><span className="muted">Seite {offset/100+1}</span><button className="btn sm" disabled={rows.length<100} onClick={()=>setOffset(offset+100)}>Ältere</button></div></div>
}
export function ProfilePanel({account,onChanged}:{account:Account,onChanged:()=>void}){
 const [oldPassword,setOldPassword]=useState('');const [newPassword,setNewPassword]=useState('');const [secret,setSecret]=useState('');const [totpUri,setTotpUri]=useState('');const [code,setCode]=useState('');const [disablePw,setDisablePw]=useState('');const [error,setError]=useState('');const [notice,setNotice]=useState('');const [busy,setBusy]=useState(false);
 async function run(f:()=>Promise<unknown>,message:string){setBusy(true);setError('');setNotice('');try{await f();setNotice(message);onChanged()}catch(e){setError(msg(e))}finally{setBusy(false)}}
 async function change(e:FormEvent){e.preventDefault();await run(()=>api('/me/change-password',{method:'POST',body:JSON.stringify({current_password:oldPassword,new_password:newPassword})}),'Passwort geändert. Bitte melden Sie sich erneut an.');setOldPassword('');setNewPassword('')}
 async function setup(){setBusy(true);setError('');try{const r=await api<{secret:string;otpauth_uri:string}>('/me/mfa/setup',{method:'POST'});setSecret(r.secret);setTotpUri(r.otpauth_uri)}catch(e){setError(msg(e))}finally{setBusy(false)}}
 async function activate(){await run(()=>api('/me/mfa/verify',{method:'POST',body:JSON.stringify({code})}),'Zwei-Faktor-Authentifizierung aktiviert. Bitte mit dem neuen Code erneut anmelden.');setSecret('');setTotpUri('');setCode('')}
 async function disable(){await run(()=>api('/me/mfa/disable',{method:'POST',body:JSON.stringify({code,current_password:disablePw})}),'Zwei-Faktor-Authentifizierung deaktiviert. Bitte erneut anmelden.');setCode('');setDisablePw('')}
 return <div className="stack narrow">{error&&<div className="callout bad"><AlertTriangle size={16}/><span>{error}</span></div>}{notice&&<div className="callout ok"><span>{notice}</span></div>}
 <section className="card"><dl className="facts"><dt>Benutzer</dt><dd>{account.username}</dd><dt>E-Mail</dt><dd>{account.email||'–'}</dd><dt>Rolle</dt><dd>{roleLabel[account.role]}</dd><dt>Anmeldung</dt><dd>{account.provider==='oidc'?'Kanzlei-Login (OIDC)':'Lokales Passwort'}</dd></dl></section>
 {account.provider==='local'?<><section className="card"><div className="card-head"><h2><KeyRound size={17}/> Passwort ändern</h2></div><form className="form" onSubmit={change}><label className="field"><span>Aktuelles Passwort</span><input type="password" autoComplete="current-password" value={oldPassword} onChange={e=>setOldPassword(e.target.value)} required/></label><label className="field"><span>Neues Passwort <em>mindestens 14 Zeichen</em></span><input type="password" autoComplete="new-password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} minLength={14} required/></label><div><button className="btn primary" disabled={busy}>Passwort ändern</button></div></form></section>
 <section className="card"><div className="card-head"><h2><ShieldCheck size={17}/> Zwei-Faktor-Anmeldung</h2>{account.mfa_enabled&&<span className="badge ok"><span className="dot"/>Aktiv</span>}</div>
 {!account.mfa_enabled&&!secret&&<div className="form"><p className="hint">Schützt das lokale Konto zusätzlich mit einem Code aus einer Authenticator-App.</p><div><button className="btn" disabled={busy} onClick={setup}>Einrichten</button></div></div>}
 {secret&&<div className="form"><p className="hint">Diesen Schlüssel in die Authenticator-App eintragen. Er wird danach nicht mehr angezeigt.</p><code className="secret">{secret}</code><details className="more"><summary>Als otpauth-Adresse</summary><code className="secret small">{totpUri}</code></details><label className="field"><span>Sechsstelliger Code</span><input inputMode="numeric" pattern="[0-9]{6}" value={code} maxLength={6} onChange={e=>setCode(e.target.value)} /></label><div><button className="btn primary" onClick={activate} disabled={busy||code.length!==6}>Aktivieren</button></div></div>}
 {account.mfa_enabled&&<div className="form"><p className="hint">Zum Abschalten werden Passwort und ein aktueller Code benötigt.</p><div className="row2"><label className="field"><span>Passwort</span><input type="password" value={disablePw} onChange={e=>setDisablePw(e.target.value)}/></label><label className="field"><span>Code</span><input inputMode="numeric" pattern="[0-9]{6}" value={code} maxLength={6} onChange={e=>setCode(e.target.value)}/></label></div><div><button className="btn danger" disabled={busy||code.length!==6||!disablePw} onClick={disable}>Abschalten</button></div></div>}
 </section></>:<p className="hint">Passwort und Zwei-Faktor-Anmeldung verwalten Sie beim Kanzlei-Login (Ihrem OIDC-Anbieter).</p>}
 </div>
}
