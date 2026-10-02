import { BottomSheet } from '@arena/ui';
import { useEffect, useState } from 'react';
import { PlayerProfileView } from './PlayerProfile.js';

/** The full player card over the table or the result screen, where page navigation is not available. */
export function ProfileSheet({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const [shown, setShown] = useState(userId);
  useEffect(() => setShown(userId), [userId]);
  return (
    <BottomSheet open={userId !== null} title="Профиль игрока" onClose={onClose}>
      <div className="profile-sheet">{shown && <PlayerProfileView key={shown} userId={shown} atTable onOpenPlayer={setShown} />}</div>
    </BottomSheet>
  );
}
