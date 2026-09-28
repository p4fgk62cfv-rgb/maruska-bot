import type { FastifyInstance } from 'fastify';

/** Session tokens travel in the WebSocket URL (`/ws?token=…`); never let them reach the logs. */
export function redactUrl(url: string | undefined): string | undefined {
  return url?.replace(/([?&](?:token|initData)=)[^&]*/gi, '$1[redacted]');
}

export const requestSerializer = (req: { method: string; url: string; hostname?: string; ip?: string }) => ({
  method: req.method,
  url: redactUrl(req.url),
  hostname: req.hostname,
  remoteAddress: req.ip,
});

/**
 * Headers for every response. The Mini App must stay embeddable by Telegram Web
 * (web.telegram.org shows it in an iframe), so framing is limited to Telegram, not denied.
 */
export function securityHeaders(app: FastifyInstance): void {
  const csp = [
    "default-src 'self'",
    "script-src 'self' https://telegram.org",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "connect-src 'self' wss: https:",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    'frame-ancestors https://web.telegram.org https://*.telegram.org',
  ].join('; ');
  app.addHook('onSend', async (_request, reply) => {
    reply.header('X-Content-Type-Options', 'nosniff');
    reply.header('Referrer-Policy', 'no-referrer');
    reply.header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    reply.header('Content-Security-Policy', csp);
  });
}
