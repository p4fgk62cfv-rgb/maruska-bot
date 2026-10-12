import { memo, useId, useState } from 'react';

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
  /** VIP: a golden crown tilted over the top corner. */
  vip?: boolean;
  status?: 'online' | 'in_game' | 'offline';
}

/** Telegram photo when available, otherwise initials on a stable per-user gradient. */
export const Avatar = memo(function Avatar({ id, name, photoUrl, size = 44, ring = 'none', status, crown, vip }: AvatarProps) {
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
      {vip && <VipCrown />}
    </span>
  );
});

/** The VIP crown: gold with a ruby and two sapphires, a pearl on each point. */
export function VipCrown({ className = 'ui-avatar__vip' }: { className?: string }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="0 0 64 52" aria-label="VIP" role="img">
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff6c2" />
          <stop offset="0.35" stopColor="#ffd84a" />
          <stop offset="0.7" stopColor="#f0a91c" />
          <stop offset="1" stopColor="#b9740a" />
        </linearGradient>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffe27a" />
          <stop offset="1" stopColor="#c27c0e" />
        </linearGradient>
        <radialGradient id={`${id}r`} cx="0.35" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#ffd1dc" />
          <stop offset="0.4" stopColor="#ff2e63" />
          <stop offset="1" stopColor="#8a0a2b" />
        </radialGradient>
        <radialGradient id={`${id}s`} cx="0.35" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#d6f3ff" />
          <stop offset="0.45" stopColor="#2f9bff" />
          <stop offset="1" stopColor="#0b3c8c" />
        </radialGradient>
        <radialGradient id={`${id}p`} cx="0.35" cy="0.3" r="0.75">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.6" stopColor="#fff1c4" />
          <stop offset="1" stopColor="#d9a93a" />
        </radialGradient>
      </defs>
      {/* body: five points, the middle one tallest */}
      <path
        d="M6 40 L3 15 L17 27 L22 9 L32 23 L42 9 L47 27 L61 15 L58 40 Z"
        fill={`url(#${id}g)`}
        stroke="#7a4706"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {/* band */}
      <rect x="5" y="38" width="54" height="10" rx="3" fill={`url(#${id}b)`} stroke="#7a4706" strokeWidth="2" />
      {/* light on the gold */}
      <path d="M9 36 L7 21 L16 30" fill="none" stroke="#fffbe0" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      {/* jewels */}
      <circle cx="32" cy="43" r="4" fill={`url(#${id}r)`} stroke="#5c0a1e" strokeWidth="1" />
      <circle cx="17" cy="43" r="2.8" fill={`url(#${id}s)`} stroke="#0b2a60" strokeWidth="0.8" />
      <circle cx="47" cy="43" r="2.8" fill={`url(#${id}s)`} stroke="#0b2a60" strokeWidth="0.8" />
      <circle cx="32" cy="30" r="3.2" fill={`url(#${id}r)`} stroke="#5c0a1e" strokeWidth="0.8" />
      {/* pearls on the points */}
      <circle cx="3" cy="14" r="3.4" fill={`url(#${id}p)`} stroke="#8a5a0c" strokeWidth="0.8" />
      <circle cx="22" cy="8" r="3.4" fill={`url(#${id}p)`} stroke="#8a5a0c" strokeWidth="0.8" />
      <circle cx="42" cy="8" r="3.4" fill={`url(#${id}p)`} stroke="#8a5a0c" strokeWidth="0.8" />
      <circle cx="61" cy="14" r="3.4" fill={`url(#${id}p)`} stroke="#8a5a0c" strokeWidth="0.8" />
      {/* sparkle */}
      <path className="ui-vip-sparkle" d="M50 4 L51.2 7.8 L55 9 L51.2 10.2 L50 14 L48.8 10.2 L45 9 L48.8 7.8 Z" fill="#fffef0" />
    </svg>
  );
}
