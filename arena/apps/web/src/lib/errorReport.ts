import { getToken } from './api.js';

/** At most this many reports per launch, each message once: a crash loop must not flood the server. */
const MAX_REPORTS = 10;
const seen = new Set<string>();

/**
 * Sends a crash in the app to the server, where the owner's «Журнал» shows it: otherwise a
 * phone's error is invisible and all we hear is «зависло».
 */
export function reportError(kind: 'error' | 'promise' | 'render', error: unknown, extra: Record<string, unknown> = {}): void {
  try {
    const message = error instanceof Error ? error.message : String(error);
    if (!message || seen.has(message) || seen.size >= MAX_REPORTS) return;
    seen.add(message);
    const token = getToken();
    if (!token) return;
    const stack = error instanceof Error ? (error.stack ?? '') : '';
    void fetch('/api/client-error', {
      method: 'POST',
      keepalive: true,
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({
        kind,
        message: message.slice(0, 300),
        stack: stack.slice(0, 1500),
        where: location.hash || location.pathname,
        version: typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '',
        agent: navigator.userAgent.slice(0, 200),
        ...extra,
      }),
    }).catch(() => undefined);
  } catch {
    // Reporting must never be the next crash.
  }
}

export function installErrorReporting(): void {
  window.addEventListener('error', (e) => reportError('error', e.error ?? e.message));
  window.addEventListener('unhandledrejection', (e) => reportError('promise', e.reason));
}
