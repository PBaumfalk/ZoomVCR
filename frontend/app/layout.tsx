import './globals.css';
import type { Metadata, Viewport } from 'next';
import { Hanken_Grotesk, IBM_Plex_Mono } from 'next/font/google';

// next/font lädt die Schriften beim Build und liefert sie selbst aus (kein Google-Aufruf im Browser).
const ui = Hanken_Grotesk({ subsets: ['latin'], variable: '--font-ui', display: 'swap' });
const mono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = { title: 'ZoomVCR', description: 'Fortbildungsrekorder der Kanzlei' };
export const viewport: Viewport = { themeColor: [{ media: '(prefers-color-scheme: light)', color: '#f4f3ef' }, { media: '(prefers-color-scheme: dark)', color: '#131417' }] };

// Gewähltes Farbschema vor dem ersten Zeichnen setzen, damit nichts aufblitzt.
const themeScript = `try{var t=localStorage.getItem('zoomvcr-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="de" className={`${ui.variable} ${mono.variable}`} suppressHydrationWarning>
    <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
    <body>{children}</body>
  </html>;
}
