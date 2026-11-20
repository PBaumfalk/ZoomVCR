// Prüft alle relativen Links und Anker in README, CHANGELOG und Handbuch.
// Anker werden wie bei GitHub gebildet: klein, Satzzeichen weg, Leerzeichen zu Bindestrichen.
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const files = ['README.md', 'CHANGELOG.md', ...readdirSync(join(ROOT, 'docs/handbuch')).filter((f) => f.endsWith('.md')).map((f) => 'docs/handbuch/' + f)];

const slug = (h) => h.trim().toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s/g, '-');
const anchors = (file) => {
  const seen = new Map();
  const text = readFileSync(file, 'utf8').replace(/```[\s\S]*?```/g, '');
  return new Set([...text.matchAll(/^#{1,6}\s+(.+)$/gm)].map((m) => {
    const s = slug(m[1]); const n = seen.get(s) || 0; seen.set(s, n + 1); return n ? `${s}-${n}` : s;
  }));
};

let errors = 0, links = 0;
for (const f of files) {
  const abs = join(ROOT, f);
  const text = readFileSync(abs, 'utf8').replace(/```[\s\S]*?```/g, '');
  for (const m of text.matchAll(/(?:\]\(|src=")([^)"\s]+)[)"]/g)) {
    const target = m[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    links++;
    const [path, hash] = target.split('#');
    const dest = path ? resolve(dirname(abs), decodeURIComponent(path)) : abs;
    if (!existsSync(dest)) { console.error(`${f}: Datei fehlt: ${target}`); errors++; continue; }
    if (hash && dest.endsWith('.md') && !anchors(dest).has(decodeURIComponent(hash))) {
      console.error(`${f}: Anker fehlt: ${target} (in ${relative(ROOT, dest)})`); errors++;
    }
  }
}
console.log(`${files.length} Dateien, ${links} Verweise geprüft, ${errors} Fehler.`);
process.exit(errors ? 1 : 0);
