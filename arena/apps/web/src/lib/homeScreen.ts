import { useCallback, useEffect, useState } from 'react';
import { haptic, tg, type HomeScreenStatus } from './telegram.js';

/**
 * «Добавить на главный экран»: Telegram (Bot API 8.0+) puts an icon of the Arena on the phone's
 * home screen; tapping it opens the Arena in Telegram at once. Telegram says whether this phone
 * supports it and whether the icon is already there — the button shows only when it helps.
 */
export function useHomeScreen(): { status: HomeScreenStatus | null; add: () => void } {
  const [status, setStatus] = useState<HomeScreenStatus | null>(null);

  useEffect(() => {
    if (!tg || !tg.isVersionAtLeast('8.0') || !tg.checkHomeScreenStatus) {
      setStatus('unsupported');
      return;
    }
    const app = tg;
    const onAdded = () => setStatus('added');
    const onChecked = (payload?: unknown) => {
      const s = (payload as { status?: HomeScreenStatus } | undefined)?.status;
      if (s) setStatus(s);
    };
    app.onEvent('homeScreenAdded', onAdded);
    app.onEvent('homeScreenChecked', onChecked);
    try {
      app.checkHomeScreenStatus?.((s) => setStatus(s));
    } catch {
      setStatus('unsupported');
    }
    return () => {
      app.offEvent('homeScreenAdded', onAdded);
      app.offEvent('homeScreenChecked', onChecked);
    };
  }, []);

  const add = useCallback(() => {
    haptic.tap();
    try {
      tg?.addToHomeScreen?.();
    } catch {
      setStatus('unsupported');
    }
  }, []);

  return { status, add };
}

/** Telegram can add the icon here and it is not there yet (or it cannot tell). */
export const canAddToHomeScreen = (status: HomeScreenStatus | null) => status === 'missed' || status === 'unknown';
