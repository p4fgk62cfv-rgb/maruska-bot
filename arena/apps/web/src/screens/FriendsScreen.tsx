import type { FriendDto } from '@arena/shared';
import { Avatar, Badge, EmptyState, Panel, RatingBadge, Tabs } from '@arena/ui';
import { useState } from 'react';
import { useQuery } from '../lib/useQuery.js';
import { QueryView, ScreenHeader } from './common.js';

const PRESENCE = { online: ['green', 'Онлайн'], in_game: ['gold', 'В игре'], offline: ['muted', 'Не в сети'] } as const;

export default function FriendsScreen() {
  const [tab, setTab] = useState<'friends' | 'requests' | 'recent'>('friends');
  const query = useQuery<FriendDto[]>('/friends');
  return (
    <div className="app-stack">
      <ScreenHeader title="Друзья" />
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'friends', label: 'Друзья' },
          { value: 'requests', label: 'Заявки' },
          { value: 'recent', label: 'Недавние' },
        ]}
      />
      {tab === 'friends' ? (
        <QueryView query={query}>
          {(list) =>
            list.length === 0 ? (
              <EmptyState icon="users" title="Пока никого" text="Сыграйте партию — соперников можно будет добавить в друзья прямо из-за стола." />
            ) : (
              <div className="app-list">
                {list.map((f) => {
                  const [tone, label] = PRESENCE[f.presence];
                  return (
                    <Panel key={f.id} className="friend-row">
                      <Avatar id={f.id} name={f.name} photoUrl={f.photoUrl} status={f.presence} />
                      <div className="friend-row__body">
                        <strong>{f.name}</strong>
                        <RatingBadge rating={f.rating} />
                      </div>
                      <Badge tone={tone}>{label}</Badge>
                    </Panel>
                  );
                })}
              </div>
            )
          }
        </QueryView>
      ) : (
        <EmptyState icon="users" title={tab === 'requests' ? 'Заявок нет' : 'Недавних игроков нет'} text="Раздел заработает вместе с приватными играми (этап 6)." />
      )}
    </div>
  );
}
