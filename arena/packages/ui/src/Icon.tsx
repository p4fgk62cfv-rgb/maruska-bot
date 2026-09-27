import type { SVGProps } from 'react';

/** One stroke icon set (24px grid, 1.8px stroke) so every screen looks consistent. */
const PATHS = {
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
  cards: 'M7 4h9a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm11.5 3.5 1.8.5a2 2 0 0 1 1.4 2.4l-2.5 9.4M11.5 9.5l-2 2.5 2 2.5 2-2.5-2-2.5Z',
  trophy: 'M8 4h8v5a4 4 0 0 1-8 0V4Zm0 2H5a3 3 0 0 0 3 4m8-4h3a3 3 0 0 1-3 4m-4 3v4m-4 3h8m-6 0 .5-3h3l.5 3',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0m1-9a3 3 0 1 0-1-5.8M17 14.5a5 5 0 0 1 4 5.5',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  lock: 'M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6v-9Zm6 4v2',
  gem: 'M6 4h12l3 5-9 11L3 9l3-5Zm-3 5h18M9.5 4 8 9l4 11 4-11-1.5-5',
  star: 'm12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z',
  news: 'M5 5h11v14H6a1 1 0 0 1-1-1V5Zm11 4h3v9a1 1 0 0 1-1 1h-2M8 9h5M8 12h5M8 15h3',
  medal: 'M8 3h8l-2 6h-4L8 3Zm4 6a6 6 0 1 1 0 12 6 6 0 0 1 0-12Zm0 3 1.2 2.2 2.3.3-1.7 1.6.4 2.4-2.2-1.1-2.2 1.1.4-2.4-1.7-1.6 2.3-.3L12 12Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.3l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2.2-1.3L14.4 3h-4l-.4 2.4a7.5 7.5 0 0 0-2.2 1.3l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.6l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2.2 1.3l.4 2.4h4l.4-2.4a7.5 7.5 0 0 0 2.2-1.3l2.4 1 2-3.4-2-1.6c.1-.4.1-.9.1-1.3Z',
  book: 'M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2V5Zm0 15a2 2 0 0 0 2 2h13v-4',
  bag: 'M5 8h14l-1 12H6L5 8Zm4 0V6a3 3 0 0 1 6 0v2',
  play: 'M8 5v14l11-7L8 5Z',
  plus: 'M12 5v14M5 12h14',
  back: 'M15 5l-7 7 7 7',
  close: 'M6 6l12 12M18 6 6 18',
  coin: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v8m-2.5-6.5h3.8a1.7 1.7 0 0 1 0 3.5H10.5a1.7 1.7 0 0 0 0 3.5h4',
  chip: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-14v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.9 2.9m7 7 2.9 2.9m0-12.8-2.9 2.9m-7 7-2.9 2.9',
  flame: 'M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-3 5-3 8a6 6 0 0 0 6 6Z',
  swap: 'M7 7h12l-3-3m3 3-3 3M17 17H5l3 3m-3-3 3-3',
  heart: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z',
  server: 'M5 4h14v6H5V4Zm0 10h14v6H5v-6Zm3-7h.01M8 17h.01',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v4l3 2',
  crown: 'M4 18h16M5 18 3.5 8l5 4L12 5l3.5 7 5-4L19 18',
  wifiOff: 'M3 3l18 18M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 4-2.4M12 20h.01M19 13a10 10 0 0 0-2.3-1.6M2 9.5a15 15 0 0 1 4.3-2.8M10.7 5.1A15 15 0 0 1 22 9.5',
  share: 'M16 6l-4-4-4 4m4-4v13M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7',
  filter: 'M4 5h16l-6 8v5l-4 2v-7L4 5Z',
} as const;

export type IconName = keyof typeof PATHS;

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 22, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
