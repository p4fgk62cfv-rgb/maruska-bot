import { memo, useState } from 'react';

const GRADIENTS = [
  ['#8b5cf6', '#22d3ee'],
  ['#a855f7', '#ec4899'],
  ['#6366f1', '#14b8a6'],
  ['#f59e0b', '#ef4444'],
  ['#0ea5e9', '#8b5cf6'],
  ['#10b981', '#6366f1'],
] as const;

function hash(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i++) h = (h * 31 + value.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export interface AvatarProps {
  id: string;
  name: string;
  photoUrl?: string | null;
  size?: number;
  ring?: 'none' | 'violet' | 'gold' | 'cyan' | 'silver';
  /** Crown item on top of the avatar. */
  crown?: boolean;
  status?: 'online' | 'in_game' | 'offline';
}

/** Telegram photo when available, otherwise initials on a stable per-user gradient. */
export const Avatar = memo(function Avatar({ id, name, photoUrl, size = 44, ring = 'none', status, crown }: AvatarProps) {
  const [from, to] = GRADIENTS[hash(id) % GRADIENTS.length]!;
  // A photo that failed to load (expired Telegram link, a network blip) falls back to the
  // initials instead of an empty circle; a new address is tried again.
  const [failed, setFailed] = useState<string | null>(null);
  const showPhoto = Boolean(photoUrl) && failed !== photoUrl;
  const initials = name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
  return (
    <span className={`ui-avatar ui-avatar--ring-${ring}`} style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {showPhoto ? (
        <img src={photoUrl!} alt="" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(photoUrl ?? null)} />
      ) : (
        <span className="ui-avatar__initials" style={{ background: `linear-gradient(135deg, ${from}, ${to})` }}>
          {initials || '?'}
        </span>
      )}
      {status && <span className={`ui-avatar__status ui-avatar__status--${status}`} />}
      {crown && (
        <span className="ui-avatar__crown" aria-label="Корона">
          ♛
        </span>
      )}
    </span>
  );
});
