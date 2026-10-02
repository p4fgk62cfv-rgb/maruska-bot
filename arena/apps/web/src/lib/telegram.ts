import { settings } from './settings.js';

/**
 * Thin typed layer over Telegram's official Mini App SDK (telegram-web-app.js).
 * Everything degrades to no-ops outside Telegram so the app still runs in a browser for development.
 */
interface SafeAreaInset { top: number; bottom: number; left: number; right: number }

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
  openLink?(url: string, options?: { try_instant_view?: boolean }): void;
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
