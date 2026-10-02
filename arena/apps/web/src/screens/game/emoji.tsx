import { EMOJI_PACKS, smilesOf, stickerUrl, type EmojiPackKey } from '@arena/shared';
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

/**
 * Compact smile picker that sits above the dock, like a speech balloon with a tab holding the
 * close button. Tapping my portrait again (marked `data-emoji-toggle`) closes it, so does a tap
 * anywhere outside. Shows the pack chosen in «Предметы».
 */
export function EmojiSheet({ open, pack, onClose, onPick }: { open: boolean; pack: string; onClose: () => void; onPick: (smile: string) => void }) {
  const def = EMOJI_PACKS[pack as EmojiPackKey] ?? EMOJI_PACKS.emoji_pack_basic;
  const smiles = smilesOf(pack);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      const target = e.target as Element | null;
      if (!target || ref.current?.contains(target) || target.closest('[data-emoji-toggle]')) return;
      onClose();
    };
    document.addEventListener('pointerdown', outside, true);
    return () => document.removeEventListener('pointerdown', outside, true);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="emoji-pop" ref={ref} role="dialog" aria-label={def.title}>
      <div className="emoji-pop__tab">
        <button type="button" className="emoji-pop__close" aria-label="Закрыть" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className={`emoji-pop__grid${def.stickers ? '' : ' emoji-pop__grid--text'}`}>
        {smiles.map((s) => (
          <button key={s} type="button" onClick={() => (onClose(), onPick(s))}>
            <Smile smile={s} />
          </button>
        ))}
      </div>
    </div>
  );
}
