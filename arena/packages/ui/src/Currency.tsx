import { useId } from 'react';

export interface CurrencyIconProps {
  kind: 'credits' | 'coins';
  size?: number;
}

/**
 * The two game currencies drawn in colour: credits are a small stack of green banknotes,
 * coins a gold coin with a diamond. Works on light and dark backgrounds alike.
 */
export function CurrencyIcon({ kind, size = 18 }: CurrencyIconProps) {
  const id = useId().replace(/:/g, '');
  if (kind === 'coins') {
    return (
      <svg className="ui-currency ui-currency--coins" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <radialGradient id={`${id}f`} cx="0.35" cy="0.3" r="0.85">
            <stop offset="0" stopColor="#ffe9a6" />
            <stop offset="0.55" stopColor="#f7a51c" />
            <stop offset="1" stopColor="#d86f08" />
          </radialGradient>
          <linearGradient id={`${id}d`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#fff8d8" />
            <stop offset="1" stopColor="#ffbe2e" />
          </linearGradient>
        </defs>
        <circle cx="16" cy="16.6" r="14.6" fill="#a84f04" />
        <circle cx="16" cy="15.4" r="14.2" fill={`url(#${id}f)`} />
        <circle cx="16" cy="15.4" r="10.6" fill="none" stroke="#ffd873" strokeOpacity="0.75" strokeWidth="1.3" />
        <rect x="10.6" y="10" width="10.8" height="10.8" rx="2.2" transform="rotate(45 16 15.4)" fill={`url(#${id}d)`} stroke="#e0850c" strokeWidth="1.1" />
        <path d="M11.6 13.4 16 9l2.2 2.2" fill="none" stroke="#fff" strokeOpacity="0.8" strokeWidth="1.1" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className="ui-currency ui-currency--credits" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#e2f5c2" />
          <stop offset="1" stopColor="#9fd066" />
        </linearGradient>
      </defs>
      <g transform="rotate(-10 16 16)">
        <rect x="2.5" y="10.5" width="27" height="16" rx="2.6" fill="#5f8f31" />
        <rect x="3" y="8.2" width="26" height="16" rx="2.6" fill="#7fb04a" />
        <rect x="3.5" y="5.8" width="25" height="16" rx="2.6" fill={`url(#${id}b)`} stroke="#4e7d25" strokeWidth="1.1" />
        <rect x="6" y="8.3" width="20" height="11" rx="1.6" fill="none" stroke="#6fa33b" strokeOpacity="0.7" strokeWidth="1" />
        <circle cx="19.5" cy="13.8" r="4.1" fill="#c8e8a0" stroke="#5a8e2c" strokeWidth="1.1" />
        <path d="M21 12.2a2.2 2.2 0 1 0 0 3.2" fill="none" stroke="#4e7d25" strokeWidth="1.2" strokeLinecap="round" />
        <rect x="8" y="11.3" width="4.5" height="1.4" rx="0.7" fill="#6fa33b" />
        <rect x="8" y="14.4" width="3" height="1.4" rx="0.7" fill="#6fa33b" />
      </g>
    </svg>
  );
}
