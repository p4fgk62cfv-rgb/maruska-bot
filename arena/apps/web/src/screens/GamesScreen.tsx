import { Button, EmptyState, Panel } from '@arena/ui';
import { useNav } from '../navigation.js';
import { ScreenHeader } from './common.js';

export default function GamesScreen() {
  const { push } = useNav();
  return (
    <div className="app-stack">
      <ScreenHeader title="Игры" subtitle="Открытые и приватные столы" />
      <Panel>
        <EmptyState
          icon="cards"
          title="Лобби откроется на этапе 2"
          text="Игровой движок уже готов на сервере. Следующий шаг — комнаты, создание игры и подключение по WebSocket."
          action={<Button variant="ghost" icon="server" onClick={() => push('servers')}>Серверы</Button>}
        />
      </Panel>
    </div>
  );
}
