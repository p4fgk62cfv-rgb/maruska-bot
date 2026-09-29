import { EMOJI_PACKS, smilesOf, stickerUrl, type EmojiPackKey } from '@arena/shared';
import { BottomSheet } from '@arena/ui';
import { useEffect, useRef, useState } from 'react';
import { play } from '../../lib/sound.js';
import { settings } from '../../lib/settings.js';
import { useRealtime } from '../../realtime.js';

/** How long a smile stays over the portrait (matches the `smile-show` keyframes). */
const SHOW_MS = 3400;

/** A smile over a portrait; `n` restarts the animation when the same smile is sent again. */
export interface SeatSmile {
  smile: string;
  n: number;
}

/** A classic emoji as text, a sticker as its picture. */
export function Smile({ smile, size }: { smile: string; size?: number }) {
  const url = stickerUrl(smile);
  if (url) return <img className="smile-img" src={url} alt="" draggable={false} style={size ? { width: size, height: size } : undefined} />;
  return <span className="smile-text" style={size ? { fontSize: size * 0.8 } : undefined}>{smile}</span>;
}

/** Smiles over portraits, at the gathering table and during a deal alike: userId → smile. */
export function useSeatEmojis(myId: string): Record<string, SeatSmile | null> {
  const { onEmoji } = useRealtime();
  const [emojis, setEmojis] = useState<Record<string, SeatSmile | null>>({});
  const counter = useRef(0);
  useEffect(
    () =>
      onEmoji((userId, smile) => {
        if (!settings.get().emojis && userId !== myId) return;
        play('emoji');
        const n = ++counter.current;
        setEmojis((e) => ({ ...e, [userId]: { smile, n } }));
        window.setTimeout(() => setEmojis((e) => (e[userId]?.n === n ? { ...e, [userId]: null } : e)), SHOW_MS);
      }),
    [onEmoji, myId],
  );
  return emojis;
}

/** The picker shows the pack chosen in «Предметы». */
export function EmojiSheet({ open, pack, onClose, onPick }: { open: boolean; pack: string; onClose: () => void; onPick: (smile: string) => void }) {
  const def = EMOJI_PACKS[pack as EmojiPackKey] ?? EMOJI_PACKS.emoji_pack_basic;
  const smiles = smilesOf(pack);
  return (
    <BottomSheet open={open} title={def.title} onClose={onClose}>
      <div className={`emoji-grid${def.stickers ? ' emoji-grid--stickers' : ''}`}>
        {smiles.map((s) => (
          <button key={s} type="button" onClick={() => (onClose(), onPick(s))}>
            <Smile smile={s} />
          </button>
        ))}
      </div>
      <p className="emoji-hint">Другие наборы смайлов — в «Предметах»</p>
    </BottomSheet>
  );
}
