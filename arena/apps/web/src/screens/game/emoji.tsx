import { EMOJIS, type Emoji } from '@arena/shared';
import { BottomSheet } from '@arena/ui';
import { useEffect, useState } from 'react';
import { play } from '../../lib/sound.js';
import { settings } from '../../lib/settings.js';
import { useRealtime } from '../../realtime.js';

/** Smiles above portraits, at the gathering table and during a deal alike: userId → emoji. */
export function useSeatEmojis(myId: string): Record<string, string> {
  const { onEmoji } = useRealtime();
  const [emojis, setEmojis] = useState<Record<string, string>>({});
  useEffect(
    () =>
      onEmoji((userId, emoji) => {
        if (!settings.get().emojis && userId !== myId) return;
        play('emoji');
        setEmojis((e) => ({ ...e, [userId]: emoji }));
        window.setTimeout(() => setEmojis((e) => (e[userId] === emoji ? { ...e, [userId]: '' } : e)), 2500);
      }),
    [onEmoji, myId],
  );
  return emojis;
}

export function EmojiSheet({ open, onClose, onPick }: { open: boolean; onClose: () => void; onPick: (emoji: Emoji) => void }) {
  return (
    <BottomSheet open={open} title="Смайлик" onClose={onClose}>
      <div className="emoji-grid">
        {EMOJIS.map((e) => (
          <button key={e} type="button" onClick={() => (onClose(), onPick(e))}>
            {e}
          </button>
        ))}
      </div>
    </BottomSheet>
  );
}
