import { useNav } from '../../navigation.js';
import { useMe } from '../../session.js';
import { ScreenHeader } from '../common.js';
import { PlayerProfileView } from './PlayerProfile.js';

/** Someone's game card, opened from friends, history or the leaderboard. */
export default function PlayerScreen() {
  const { playerId, openPlayer, push } = useNav();
  const me = useMe();
  if (!playerId) return null;
  return (
    <div className="app-stack">
      <ScreenHeader title={playerId === me.id ? 'Мой профиль' : 'Игрок'} />
      <PlayerProfileView key={playerId} userId={playerId} onOpenPlayer={openPlayer} onAchievements={playerId === me.id ? () => push('achievements') : undefined} />
    </div>
  );
}
