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

export const isAndroid = /android/i.test(navigator.userAgent);

export const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

/** «Android · Chrome», «iPhone · Safari» — shown by the bot before the sign-in is confirmed. */
export function deviceName(): string {
  const ua = navigator.userAgent;
  const os = /android/i.test(ua) ? 'Android' : /iphone/i.test(ua) ? 'iPhone' : /ipad/i.test(ua) || isIOS ? 'iPad' : /windows/i.test(ua) ? 'Windows' : /mac os/i.test(ua) ? 'Mac' : /linux/i.test(ua) ? 'Linux' : 'Устройство';
  const browser = /yabrowser/i.test(ua) ? 'Яндекс Браузер' : /samsungbrowser/i.test(ua) ? 'Samsung Internet' : /edg\//i.test(ua) ? 'Edge' : /opr\//i.test(ua) ? 'Opera' : /firefox|fxios/i.test(ua) ? 'Firefox' : /crios|chrome/i.test(ua) ? 'Chrome' : /safari/i.test(ua) ? 'Safari' : 'браузер';
  return `${os} · ${browser}${isStandalone() ? ' · приложение' : ''}`;
}

// ── iPhone installed-app height bug ──

/**
 * In the installed app iOS lays the page out in a viewport shorter than the screen by the status
 * bar height, so everything pinned to the bottom (the tab bar, the table) stops short of the edge.
 * Measure the gap and hand it to CSS as --ios-gap: full-screen layers stretch by it.
 */
function fixIOSViewport(): void {
  if (inTelegram || !isIOS || !isStandalone()) return;
  const probe = document.createElement('div');
  probe.style.cssText = 'position:fixed;top:0;bottom:0;left:0;width:1px;visibility:hidden;pointer-events:none';
  document.body.appendChild(probe);
  const measure = () => {
    const portrait = window.innerHeight >= window.innerWidth;
    const screenH = portrait ? Math.max(screen.width, screen.height) : Math.min(screen.width, screen.height);
    const gap = Math.round(screenH - probe.getBoundingClientRect().height);
    // Only the status-bar-sized shortfall; anything else (keyboard, split view) is real.
    document.documentElement.style.setProperty('--ios-gap', gap > 0 && gap < 80 ? `${gap}px` : '0px');
  };
  measure();
  // iOS fixes its viewport by itself a moment later (often without a resize event): follow the
  // probe's own size, so the correction drops back to 0 as soon as the gap is gone.
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(probe);
  window.addEventListener('resize', measure);
  window.addEventListener('orientationchange', () => setTimeout(measure, 300));
  document.addEventListener('visibilitychange', () => setTimeout(measure, 100));
  window.addEventListener('pageshow', () => setTimeout(measure, 100));
  // And a few checks during the first seconds, in case nothing fires at all.
  for (const ms of [100, 300, 700, 1500, 3000, 6000]) setTimeout(measure, ms);
}

if (document.body) fixIOSViewport();
else document.addEventListener('DOMContentLoaded', fixIOSViewport);

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
export function useInstall(): { mode: 'prompt' | 'ios' | 'android' | null; install: () => Promise<void> } {
  const [, tick] = useState(0);
  useEffect(() => {
    const l = () => tick((n) => n + 1);
    listeners.add(l);
    return () => void listeners.delete(l);
  }, []);
  const mode = inTelegram || isStandalone() ? null : deferred ? 'prompt' : isIOS ? 'ios' : isAndroid ? 'android' : null;
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
