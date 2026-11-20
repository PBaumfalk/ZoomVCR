// Erzeugt die Bildschirmfotos für README und Handbuch aus einer Beispielinstanz.
// Aufruf: npm run docs:screenshots   (vorher einmal: npm install && npm --prefix frontend install)
// Startet Next im Entwicklungsmodus, die Beispiel-API (mock-api.mjs) und fotografiert mit Playwright.
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'docs', 'screenshots');
const ASSETS = mkdtempSync(join(tmpdir(), 'zoomvcr-shots-'));
mkdirSync(OUT, { recursive: true });

const procs = [];
const start = (cmd, args, opts) => { const p = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'inherit'], ...opts }); procs.push(p); return p; };
const cleanup = () => { for (const p of procs) p.kill('SIGTERM'); rmSync(ASSETS, { recursive: true, force: true }); };
process.on('exit', cleanup);
process.on('SIGINT', () => process.exit(130));

async function waitFor(url, ms = 120e3) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { const r = await fetch(url); if (r.status < 500) return; } catch { /* noch nicht da */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('Zeitüberschreitung: ' + url);
}

const browser = await chromium.launch({ args: ['--lang=de-DE'] });

// 1. Beispielmaterial (Video als WebM: das Chromium von Playwright spielt kein H.264): Folien, Live-Bild des Rekorders, kurzes Video
const slideHtml = (title, sub, n) => `<html><body style="margin:0;width:1280px;height:720px;font-family:Helvetica,Arial,sans-serif;background:#fbfaf7;color:#22252b;display:flex;flex-direction:column;justify-content:center;padding:0 110px;box-sizing:border-box">
  <div style="font-size:22px;color:#8a6a3c;letter-spacing:.04em">FORTBILDUNG ARBEITSRECHT · ${n}</div>
  <h1 style="font-size:64px;margin:18px 0 12px">${title}</h1><div style="font-size:32px;color:#555">${sub}</div>
  <div style="position:absolute;left:110px;right:110px;bottom:70px;border-top:3px solid #c9b48f"></div></body></html>`;
const slides = [
  ['Kündigungsschutz kompakt', 'Agenda und Überblick'], ['Wartezeit und Kleinbetrieb', '§ 1 Abs. 1, § 23 KSchG'],
  ['Verhaltensbedingte Kündigung', 'Abmahnung und Prognoseprinzip'], ['Betriebsbedingte Kündigung', 'Sozialauswahl nach § 1 Abs. 3 KSchG'],
  ['Anhörung des Betriebsrats', '§ 102 BetrVG'], ['Klagefrist', '§ 4 KSchG – drei Wochen'],
];
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  for (const [i, [t, s]] of slides.entries()) {
    await page.setContent(slideHtml(t, s, i + 1));
    await page.screenshot({ path: join(ASSETS, `slide-${i}.png`) });
  }
  // Testfolien wie bei der Testaufnahme ohne Zoom
  for (const [i, [t, bg]] of [['FOLIE 1 - ARBEITSRECHT', '#13213a'], ['FOLIE 2 - RECHTSPRECHUNG', '#175a4c'], ['FOLIE 3 - PRAXISHINWEISE', '#6b4630']].entries()) {
    await page.setContent(`<html><body style="margin:0;width:1280px;height:720px;background:${bg};color:#fff;display:flex;align-items:center;justify-content:center;font-family:'DejaVu Sans',Arial,sans-serif;font-size:44px">${t}</body></html>`);
    await page.screenshot({ path: join(ASSETS, `test-${i}.png`) });
  }
  const tiles = ['MK', 'JS', 'AL', 'TW'].map((x) => `<div style="height:96px;border-radius:8px;background:#2b2f36;display:flex;align-items:center;justify-content:center;color:#ddd;font-size:28px">${x}</div>`).join('');
  const slideImg = 'data:image/png;base64,' + readFileSync(join(ASSETS, 'slide-2.png')).toString('base64');
  await page.setContent(`<html><body style="margin:0;width:1280px;height:720px;background:#1a1c20;display:grid;grid-template-columns:1fr 200px;gap:12px;padding:12px;box-sizing:border-box;font-family:Helvetica,sans-serif">
    <div style="display:flex;align-items:center;justify-content:center"><img src="${slideImg}" style="width:100%;border-radius:4px"></div>
    <div style="display:flex;flex-direction:column;gap:10px">${tiles}</div></body></html>`);
  await page.screenshot({ path: join(ASSETS, 'snapshot.png') });
  await page.close();
}
execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-loop', '1', '-i', join(ASSETS, 'slide-3.png'), '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono',
  '-t', '6', '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '40', '-c:a', 'libopus', '-shortest', join(ASSETS, 'video.webm')]);

execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-loop', '1', '-i', join(ASSETS, 'test-0.png'), '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
  '-t', '59', '-r', '1', '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '40', '-c:a', 'libopus', '-shortest', join(ASSETS, 'test.webm')]);

// 2. Next und Beispiel-API starten
const env = { ...process.env, ASSETS, NEXT_TELEMETRY_DISABLED: '1' };
start('npx', ['next', 'dev', '-p', '3101'], { cwd: join(ROOT, 'frontend'), env });
start('node', [join(ROOT, 'scripts/docs/mock-api.mjs')], { env: { ...env, PORT: '3100' } });
start('node', [join(ROOT, 'scripts/docs/mock-api.mjs')], { env: { ...env, PORT: '3102', LOGGEDOUT: '1' } });
await waitFor('http://127.0.0.1:3101/');
await waitFor('http://127.0.0.1:3100/api/me');

// 3. Fotos
async function session({ dark = false, mobile = false, base = 'http://127.0.0.1:3100' } = {}) {
  const ctx = await browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    deviceScaleFactor: 2, colorScheme: dark ? 'dark' : 'light', locale: 'de-DE', timezoneId: 'Europe/Berlin',
    isMobile: mobile, hasTouch: mobile,
  });
  const page = await ctx.newPage();
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  await page.addStyleTag({ content: 'nextjs-portal{display:none!important} *{caret-color:transparent!important}' });
  return { ctx, page };
}
const shot = async (page, name, opts = {}) => { await page.waitForTimeout(400); await page.screenshot({ path: join(OUT, name + '.png'), ...opts }); console.log('  ' + name + '.png'); };
const nav = (page, label) => page.locator('aside.sidebar nav button', { hasText: label }).first().click();
const open = async (page, title) => { await nav(page, 'Mediathek'); await page.locator('.rec-row', { hasText: title }).click(); await page.waitForLoadState('networkidle'); };

console.log('Bildschirmfotos nach docs/screenshots:');
{
  const { ctx, page } = await session({ base: 'http://127.0.0.1:3102' });
  await page.locator('.login').waitFor();
  await shot(page, 'anmeldung');
  await ctx.close();
}
for (const dark of [false, true]) {
  const { ctx, page } = await session({ dark });
  const s = dark ? '-dunkel' : '';
  await page.locator('.live-card').first().waitFor();
  await shot(page, 'uebersicht' + s);
  if (!dark) {
    await nav(page, 'Mediathek'); await shot(page, 'mediathek');
    await page.getByRole('button', { name: 'Aufnahme planen' }).first().click();
    await page.locator('.modal input').first().fill('Webinar: Urlaubsrecht aktuell');
    await page.locator('.modal input[type=url], .modal input[placeholder*="zoom"]').first().fill('https://us06web.zoom.us/j/81234567890?pwd=Beispiel').catch(() => {});
    await page.locator('.modal label.check input').check();
    await page.locator('.modal input').first().focus();
    await shot(page, 'aufnahme-planen');
    await page.keyboard.press('Escape');
    // Erster Ablauf: Testaufnahme planen
    await page.getByRole('button', { name: 'Aufnahme planen' }).first().click();
    await page.locator('.modal input').first().fill('Testaufnahme Probelauf');
    await page.locator('.modal details.more summary').click();
    await page.locator('.modal details.more select').selectOption('synthetic');
    await page.locator('.modal input[type=number]').fill('1');
    await page.locator('.modal label.check input').check();
    await shot(page, 'testaufnahme-planen');
    await page.keyboard.press('Escape');
    await open(page, 'Testaufnahme Probelauf'); await page.locator('.slide, figure, .slides').first().waitFor().catch(() => {});
    await page.mouse.move(1400, 880); await page.waitForTimeout(1200);
    await shot(page, 'testaufnahme-fertig');
  }
  await open(page, 'Kündigungsschutz kompakt');
  await page.locator('.summary').waitFor();
  await page.evaluate(() => new Promise((ok) => { const v = document.querySelector('video'); if (!v) return ok(); v.addEventListener('seeked', () => ok(), { once: true }); v.currentTime = 2; }));
  await page.mouse.move(1400, 880);
  await page.waitForTimeout(1500);   // Ladekreis des Players abwarten
  await shot(page, 'aufnahme-auswertung' + s);
  if (!dark) {
    await page.getByRole('tab', { name: /Transkript/ }).click();
    await page.locator('.side-body input').fill('Abmahnung');
    await shot(page, 'aufnahme-transkript');
    await page.locator('details.menu summary').click();
    await shot(page, 'aufnahme-herunterladen', { clip: { x: 0, y: 0, width: 1440, height: 420 } });
    await page.locator('details.menu summary').click();
    await open(page, 'Fachanwaltsfortbildung'); await page.locator('figure.preview img').waitFor(); await shot(page, 'aufnahme-live');
    await open(page, 'Sozialversicherungsrecht'); await shot(page, 'aufnahme-fehler', { clip: { x: 0, y: 0, width: 1440, height: 520 } });
    await nav(page, 'Benutzer'); await page.locator('.table').first().waitFor(); await shot(page, 'benutzer');
    await nav(page, 'Auditprotokoll'); await page.locator('.table').first().waitFor(); await shot(page, 'auditprotokoll');
    await nav(page, 'KI und Benachrichtigung'); await page.locator('.card').first().waitFor(); await shot(page, 'ki-und-benachrichtigung');
    await page.locator('button.account').click(); await shot(page, 'mein-konto');
  }
  await ctx.close();
}
{
  const { ctx, page } = await session({ mobile: true });
  await page.locator('.live-card').first().waitFor();
  await shot(page, 'handy-uebersicht');
  await page.locator('.rec-row', { hasText: 'Kündigungsschutz' }).click();
  await page.locator('.summary').waitFor();
  await shot(page, 'handy-aufnahme');
  await ctx.close();
}
await browser.close();
process.exit(0);
