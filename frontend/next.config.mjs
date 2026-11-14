/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // CI already runs `npm run lint` with the flat-config plugin from #217.
  // `next build`'s bundled lint pass does not detect that plugin and would
  // only warn, so it is skipped here.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
