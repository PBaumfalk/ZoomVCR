/** @type {import('next').NextConfig} */
// outputFileTracingRoot: frontend/ ist die Wurzel, auch wenn darüber eine package-lock.json (Handbuch-Werkzeuge) liegt.
const nextConfig = { output: 'standalone', poweredByHeader: false, outputFileTracingRoot: import.meta.dirname };
export default nextConfig;
