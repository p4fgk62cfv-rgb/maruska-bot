import { Tile } from '@arena/ui';
import { useNav } from '../navigation.js';
import { ScreenHeader } from './common.js';

export default function MoreScreen() {
  const { push } = useNav();
  return (
    <div className="app-stack">
      <ScreenHeader title="Ещё" />
      <div className="app-list">
        <Tile icon="user" title="Профиль" hint="Статистика и история баланса" onClick={() => push('profile')} />
        <Tile icon="star" title="Достижения" tone="gold" onClick={() => push('achievements')} />
        <Tile icon="bag" title="Предметы" tone="rose" onClick={() => push('items')} />
        <Tile icon="server" title="Серверы" tone="cyan" onClick={() => push('servers')} />
        <Tile icon="medal" title="Доска почёта" tone="gold" onClick={() => push('leaderboard')} />
        <Tile icon="news" title="Новости" tone="cyan" onClick={() => push('news')} />
        <Tile icon="settings" title="Настройки" onClick={() => push('settings')} />
        <Tile icon="book" title="Правила" tone="green" onClick={() => push('rules')} />
      </div>
    </div>
  );
}
