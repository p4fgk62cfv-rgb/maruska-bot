import type { AvatarProps } from '@arena/ui';

/** Item key → how it looks. Keys come from the server catalogue (apps/api/src/services/catalog.ts). */
export function backOf(itemKey: string | null | undefined): string {
  return itemKey?.replace(/^back_/, '') || 'classic';
}

export function tableOf(itemKey: string | null | undefined): string {
  return itemKey?.replace(/^table_/, '') || 'felt';
}

export function ringOf(frame: string | null | undefined): AvatarProps['ring'] {
  if (frame === 'frame_gold') return 'gold';
  if (frame === 'frame_silver') return 'silver';
  return 'none';
}
