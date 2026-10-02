import { useEffect, useState } from 'react';
import { tg } from './telegram.js';

/**
 * The installed app «Арена» (PWA): the same Arena opened from the phone's home screen instead
 * of Telegram. Here: install prompt, «am I installed», the remembered sign-in.
 */

export const inTelegram = tg !== null;

export function isStandalone(): boolean {
  return window.matchMedia?.('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

/** «Android · Chrome», «iPhone · Safari» — shown by the bot before the sign-in is confirmed. */
export function deviceName(): string {
  const ua = navigator.userAgent;
  const os = /android/i.test(ua) ? 'Android' : /iphone/i.test(ua) ? 'iPhone' : /ipad/i.test(ua) || isIOS ? 'iPad' : /windows/i.test(ua) ? 'Windows' : /mac os/i.test(ua) ? 'Mac' : /linux/i.test(ua) ? 'Linux' : 'Устройство';
  const browser = /yabrowser/i.test(ua) ? 'Яндекс Браузер' : /samsungbrowser/i.test(ua) ? 'Samsung Internet' : /edg\//i.test(ua) ? 'Edge' : /opr\//i.test(ua) ? 'Opera' : /firefox|fxios/i.test(ua) ? 'Firefox' : /crios|chrome/i.test(ua) ? 'Chrome' : /safari/i.test(ua) ? 'Safari' : 'браузер';
  return `${os} · ${browser}${isStandalone() ? ' · приложение' : ''}`;
}

// ── remembered sign-in (outside Telegram only) ──

const SESSION_KEY = 'arena.appSession';

export interface SavedSession {
  token: string;
  expiresAt: number;
}

export const savedSession = {
  get(): SavedSession | null {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as SavedSession) : null;
    } catch {
      return null;
    }
  },
  set(value: SavedSession): void {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } catch {
      /* private mode: sign in again next time */
    }
  },
  clear(): void {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      /* nothing stored */
    }
  },
};

// ── install prompt ──

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

if (!inTelegram) {
  // Android / desktop Chrome offer installation; keep the offer for our own button.
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferred = event as InstallPromptEvent;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    notify();
  });
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => void navigator.serviceWorker.register('/sw.js').catch(() => undefined));
  }
}

/** What install help to show: a real «Установить» button, the iPhone steps, or nothing. */
export function useInstall(): { mode: 'prompt' | 'ios' | null; install: () => Promise<void> } {
  const [, tick] = useState(0);
  useEffect(() => {
    const l = () => tick((n) => n + 1);
    listeners.add(l);
    return () => void listeners.delete(l);
  }, []);
  const mode = inTelegram || isStandalone() ? null : deferred ? 'prompt' : isIOS ? 'ios' : null;
  return {
    mode,
    install: async () => {
      if (!deferred) return;
      await deferred.prompt();
      await deferred.userChoice.catch(() => undefined);
      deferred = null;
      notify();
    },
  };
}
