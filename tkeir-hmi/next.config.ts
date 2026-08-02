import type { NextConfig } from "next";

/**
 * Standalone output is required for the hardened container image
 * (`deploy/images/Dockerfile.tkeir-hmi`). Local `npm run dev` is unchanged.
 *
 * API access stays server-side via `API_URL` + the App Router proxy — do not
 * switch containers to `NEXT_PUBLIC_API_URL`.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              // Keycloak token refresh / discovery happens in-browser.
              "connect-src 'self' http://localhost:8082 https://kc.local",
              // Silent-check iframe needs to talk to Keycloak.
              "frame-src 'self' http://localhost:8082 https://kc.local",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
