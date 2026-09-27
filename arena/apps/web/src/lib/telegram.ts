/**
 * Thin typed layer over Telegram's official Mini App SDK (telegram-web-app.js).
 * Everything degrades to no-ops outside Telegram so the app still runs in a browser for development.
 */
interface SafeAreaInset { top: number; bottom: number; left: number; right: number }

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
  onEvent(event: string, handler: () => void): void;
  offEvent(event: string, handler: () => void): void;
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

export const haptic = {
  tap: () => tg?.HapticFeedback.impactOccurred('light'),
  select: () => tg?.HapticFeedback.selectionChanged(),
  success: () => tg?.HapticFeedback.notificationOccurred('success'),
  error: () => tg?.HapticFeedback.notificationOccurred('error'),
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
