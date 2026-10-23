import { settings } from './settings.js';

/**
 * Thin typed layer over Telegram's official Mini App SDK (telegram-web-app.js).
 * Everything degrades to no-ops outside Telegram so the app still runs in a browser for development.
 */
interface SafeAreaInset { top: number; bottom: number; left: number; right: number }

export type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending';

export type HomeScreenStatus = 'unsupported' | 'unknown' | 'added' | 'missed';

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { start_param?: string };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  viewportStableHeight: number;
  safeAreaInset?: SafeAreaInset;
  contentSafeAreaInset?: SafeAreaInset;
  ready(): void;
  expand(): void;
  isVersionAtLeast(version: string): boolean;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
  lockOrientation?(): void;
  openTelegramLink(url: string): void;
  /** Bot API 6.1: Telegram's own payment form for an invoice link. */
  openInvoice?(url: string, callback?: (status: InvoiceStatus) => void): void;
  /** try_browser: Telegram opens the link in that browser (if installed) instead of its own window. */
  openLink?(url: string, options?: { try_instant_view?: boolean; try_browser?: string }): void;
  onEvent(event: string, handler: (payload?: unknown) => void): void;
  offEvent(event: string, handler: (payload?: unknown) => void): void;
  /** Bot API 8.0: a shortcut to the Mini App on the phone's home screen. */
  addToHomeScreen?(): void;
  checkHomeScreenStatus?(callback?: (status: HomeScreenStatus) => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | null = window.Telegram?.WebApp?.initData ? window.Telegram.WebApp : null;

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
  const at = (v: string) => tg.isVersionAtLeast(v);
  if (at('6.1')) {
    tg.setHeaderColor('#0a1030');
    tg.setBackgroundColor('#050816');
  }
  if (at('7.10')) tg.setBottomBarColor?.('#050816');
  if (at('7.7')) tg.disableVerticalSwipes?.();
  if (at('8.0')) tg.lockOrientation?.();

  const applyInsets = () => {
    const root = document.documentElement.style;
    const top = (tg.safeAreaInset?.top ?? 0) + (tg.contentSafeAreaInset?.top ?? 0);
    root.setProperty('--tg-safe-top', `${top}px`);
    root.setProperty('--tg-safe-bottom', `${tg.safeAreaInset?.bottom ?? 0}px`);
    root.setProperty('--tg-viewport-h', `${tg.viewportStableHeight}px`);
  };
  applyInsets();
  for (const event of ['safeAreaChanged', 'contentSafeAreaChanged', 'viewportChanged']) tg.onEvent(event, applyInsets);
}

/** While a game runs, closing the Mini App by a stray swipe asks first. */
export function confirmClosing(on: boolean): void {
  if (!tg || !tg.isVersionAtLeast('6.2')) return;
  if (on) tg.enableClosingConfirmation();
  else tg.disableClosingConfirmation();
}

/**
 * Telegram before 7.7 cannot switch off its own «swipe down to minimise»: a finger dragging a card
 * downwards over the table folded the whole app. While the table is open, a touch that would only
 * move the page (nothing under the finger scrolls) is kept from Telegram. Lists and chats inside
 * the table still scroll. Newer Telegram does this itself (disableVerticalSwipes).
 */
export function holdSwipes(): () => void {
  if (!tg || tg.isVersionAtLeast('7.7')) return () => undefined;
  const scrolls = (el: Element | null): boolean => {
    for (; el && el !== document.body; el = el.parentElement) {
      const y = getComputedStyle(el).overflowY;
      if ((y === 'auto' || y === 'scroll') && el.scrollHeight > el.clientHeight) return true;
    }
    return false;
  };
  const onMove = (e: TouchEvent) => {
    if (e.cancelable && !scrolls(e.target as Element | null)) e.preventDefault();
  };
  document.addEventListener('touchmove', onMove, { passive: false });
  return () => document.removeEventListener('touchmove', onMove);
}

const vibrate = (fn: () => void) => {
  if (tg && settings.get().vibration) fn();
};

export const haptic = {
  tap: () => vibrate(() => tg!.HapticFeedback.impactOccurred('light')),
  heavy: () => vibrate(() => tg!.HapticFeedback.impactOccurred('medium')),
  select: () => vibrate(() => tg!.HapticFeedback.selectionChanged()),
  success: () => vibrate(() => tg!.HapticFeedback.notificationOccurred('success')),
  warning: () => vibrate(() => tg!.HapticFeedback.notificationOccurred('warning')),
  error: () => vibrate(() => tg!.HapticFeedback.notificationOccurred('error')),
};

export function setBackButton(handler: (() => void) | null): () => void {
  if (!tg) return () => undefined;
  if (!handler) {
    tg.BackButton.hide();
    return () => undefined;
  }
  tg.BackButton.onClick(handler);
  tg.BackButton.show();
  return () => {
    tg.BackButton.offClick(handler);
    tg.BackButton.hide();
  };
}

/**
 * Opens Telegram's payment form and resolves with how it ended. Outside Telegram the link opens in
 * a new tab and the result is unknown («pending»): the caller then watches the order itself.
 */
export function openInvoice(link: string): Promise<InvoiceStatus> {
  if (tg?.openInvoice && tg.isVersionAtLeast('6.1')) {
    const open = tg.openInvoice.bind(tg);
    return new Promise((resolve) => open(link, resolve));
  }
  window.open(link, '_blank', 'noopener');
  return Promise.resolve('pending');
}
