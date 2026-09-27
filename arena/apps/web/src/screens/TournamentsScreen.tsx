import type { TournamentDto } from '@arena/shared';
import { Badge, Balance, EmptyState, Panel, Tabs } from '@arena/ui';
import { useState } from 'react';
import { useQuery } from '../lib/useQuery.js';
import { QueryView, ScreenHeader } from './common.js';

const STATUS = {
  ANNOUNCED: ['cyan', 'Скоро'],
  REGISTRATION: ['green', 'Регистрация'],
  RUNNING: ['violet', 'Идёт'],
  FINISHED: ['muted', 'Завершён'],
  CANCELLED: ['red', 'Отменён'],
} as const;

export default function TournamentsScreen() {
  const [tab, setTab] = useState<'active' | 'finished'>('active');
  const query = useQuery<TournamentDto[]>(`/tournaments?status=${tab}`);
  return (
    <div className="app-stack">
      <ScreenHeader title="Турниры" />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'active', label: 'Активные' }, { value: 'finished', label: 'Завершённые' }]} />
      <QueryView query={query}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState icon="trophy" title="Турниров пока нет" text="Первый турнир объявим в боте Маруська." />
          ) : (
            <div className="app-list">
              {list.map((t) => {
                const [tone, label] = STATUS[t.status];
                return (
                  <Panel key={t.id} glow={t.status === 'RUNNING' ? 'violet' : 'none'} className="tour-card">
                    <div className="app-row app-row--between">
                      <strong>{t.title}</strong>
                      <Badge tone={tone}>{label}</Badge>
                    </div>
                    <div className="tour-card__grid">
                      <span>Призовой фонд</span>
                      <Balance kind="credits" value={t.prizePool} compact />
                      <span>Взнос</span>
                      <Balance kind="credits" value={t.entryFee} compact />
                      <span>Участники</span>
                      <strong>{t.players}/{t.maxPlayers}</strong>
                      <span>Начало</span>
                      <strong>{new Date(t.startsAt).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</strong>
                    </div>
                  </Panel>
                );
              })}
            </div>
          )
        }
      </QueryView>
    </div>
  );
}
