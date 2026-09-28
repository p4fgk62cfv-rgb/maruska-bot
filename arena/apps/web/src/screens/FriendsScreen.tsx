import type { FriendDto, FriendRequestsDto, RecentPlayerDto, Relation, SearchUserDto, SendRequestResult } from '@arena/shared';
import { Avatar, Badge, BottomSheet, Button, EmptyState, Panel, RatingBadge, SwipeRow, Tabs } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useRealtime } from '../realtime.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const PRESENCE = { online: ['green', 'Онлайн'], in_game: ['gold', 'В игре'], offline: ['muted', 'Не в сети'] } as const;

export default function FriendsScreen() {
  const { requestCount } = useRealtime();
  const [tab, setTab] = useState<'friends' | 'requests' | 'recent'>(requestCount ? 'requests' : 'friends');
  return (
    <div className="app-stack">
      <ScreenHeader title="Друзья" />
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'friends', label: 'Друзья' },
          { value: 'requests', label: requestCount ? `Заявки · ${requestCount}` : 'Заявки' },
          { value: 'recent', label: 'Недавние' },
        ]}
      />
      {tab === 'friends' && <FriendsTab />}
      {tab === 'requests' && <RequestsTab />}
      {tab === 'recent' && <RecentTab />}
    </div>
  );
}

function useAction() {
  const toast = useToast();
  return async (run: () => Promise<unknown>, done?: string) => {
    try {
      await run();
      if (done) toast(done, 'success');
      return true;
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
      return false;
    }
  };
}

function FriendsTab() {
  const query = useQuery<FriendDto[]>('/friends');
  const { room } = useRealtime();
  const act = useAction();
  const [picked, setPicked] = useState<FriendDto | null>(null);
  const inRoom = room?.status === 'waiting';

  const remove = async (f: FriendDto) => {
    if (await act(() => api(`/friends/${f.id}`, { method: 'DELETE' }), `${f.name} удалён из друзей`)) query.reload();
  };

  return (
    <>
      <SearchBox />
      <QueryView query={query}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState icon="users" title="Пока никого" text="Найдите друга по @username или добавьте соперника из «Недавних»." />
          ) : (
            <div className="app-list">
              {list.map((f) => {
                const [tone, label] = PRESENCE[f.presence];
                return (
                  <SwipeRow key={f.id} actionLabel="Удалить" onAction={() => void remove(f)}>
                    <Panel className="friend-row" role="button" tabIndex={0} onClick={() => setPicked(f)}>
                      <Avatar id={f.id} name={f.name} photoUrl={f.photoUrl} status={f.presence} />
                      <div className="friend-row__body">
                        <strong>{f.name}</strong>
                        <RatingBadge rating={f.rating} showValue={false} />
                      </div>
                      <Badge tone={tone}>{label}</Badge>
                    </Panel>
                  </SwipeRow>
                );
              })}
              <p className="app-muted">Проведите по другу справа налево, чтобы удалить.</p>
            </div>
          )
        }
      </QueryView>

      <BottomSheet open={picked !== null} title={picked?.name} onClose={() => setPicked(null)}>
        {picked && (
          <div className="app-stack">
            <Button
              block
              icon="play"
              disabled={!inRoom}
              onClick={() => void act(() => api(`/friends/${picked.id}/invite`, { method: 'POST' }), 'Приглашение отправлено').then(() => setPicked(null))}
            >
              Пригласить в игру
            </Button>
            {!inRoom && <p className="app-muted">Сначала создайте игру — тогда друга можно позвать за свой стол.</p>}
            <Button block variant="danger" onClick={() => void remove(picked).then(() => setPicked(null))}>
              Удалить из друзей
            </Button>
          </div>
        )}
      </BottomSheet>
    </>
  );
}

function SearchBox() {
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(q.trim()), 350);
    return () => window.clearTimeout(id);
  }, [q]);
  const query = useQuery<SearchUserDto[]>(debounced.replace(/^@/, '').length >= 3 ? `/users/search?q=${encodeURIComponent(debounced)}` : null);
  return (
    <div className="app-stack">
      <input className="app-input" placeholder="Найти по @username" value={q} onChange={(e) => setQ(e.target.value)} autoCapitalize="none" />
      {query.data && (
        <div className="app-list">
          {query.data.length === 0 && <p className="app-muted">Никого не нашли.</p>}
          {query.data.map((u) => (
            <PersonRow key={u.id} user={u} relation={u.relation} hint={u.username ? `@${u.username}` : undefined} />
          ))}
        </div>
      )}
    </div>
  );
}

function RequestsTab() {
  const query = useQuery<FriendRequestsDto>('/friends/requests');
  const { refreshRequests } = useRealtime();
  const act = useAction();
  const reload = () => {
    query.reload();
    refreshRequests();
  };
  return (
    <QueryView query={query}>
      {({ incoming, outgoing }) =>
        incoming.length + outgoing.length === 0 ? (
          <EmptyState icon="users" title="Заявок нет" text="Здесь появятся приглашения дружить." />
        ) : (
          <div className="app-list">
            {incoming.map((r) => (
              <Panel key={r.id} className="friend-row">
                <Avatar id={r.user.id} name={r.user.name} photoUrl={r.user.photoUrl} />
                <div className="friend-row__body">
                  <strong>{r.user.name}</strong>
                  <span className="app-muted">хочет дружить</span>
                </div>
                <div className="app-row">
                  <Button size="sm" onClick={() => void act(() => api(`/friends/requests/${r.id}/accept`, { method: 'POST' }), 'Теперь вы друзья').then(reload)}>
                    Принять
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => api(`/friends/requests/${r.id}/decline`, { method: 'POST' })).then(reload)}>
                    ✕
                  </Button>
                </div>
              </Panel>
            ))}
            {outgoing.length > 0 && <h3 className="app-section">Вы отправили</h3>}
            {outgoing.map((r) => (
              <Panel key={r.id} className="friend-row">
                <Avatar id={r.user.id} name={r.user.name} photoUrl={r.user.photoUrl} />
                <div className="friend-row__body">
                  <strong>{r.user.name}</strong>
                  <span className="app-muted">ждём ответа</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => void act(() => api(`/friends/requests/${r.id}`, { method: 'DELETE' })).then(reload)}>
                  Отменить
                </Button>
              </Panel>
            ))}
          </div>
        )
      }
    </QueryView>
  );
}

function RecentTab() {
  const query = useQuery<RecentPlayerDto[]>('/friends/recent');
  return (
    <QueryView query={query}>
      {(list) =>
        list.length === 0 ? (
          <EmptyState icon="cards" title="Недавних соперников нет" text="Сыграйте партию — соперники появятся здесь." />
        ) : (
          <div className="app-list">
            {list.map((p) => (
              <PersonRow
                key={p.id}
                user={p}
                relation={p.relation}
                hint={`${p.games} ${p.games === 1 ? 'игра' : p.games < 5 ? 'игры' : 'игр'} · ${new Date(p.lastPlayedAt).toLocaleDateString('ru-RU')}`}
              />
            ))}
          </div>
        )
      }
    </QueryView>
  );
}

const RELATION_LABEL: Partial<Record<Relation, string>> = { friend: 'Друг', outgoing: 'Заявка отправлена', incoming: 'Ждёт ответа', self: 'Вы' };

/** A player with an «Добавить» button that follows the friendship state. */
export function PersonRow({ user, relation, hint }: { user: { id: string; name: string; photoUrl: string | null; rating: number }; relation: Relation; hint?: string }) {
  const [state, setState] = useState(relation);
  const act = useAction();
  const add = async () => {
    let status: SendRequestResult['status'] | null = null;
    await act(async () => {
      status = (await api<SendRequestResult>('/friends/requests', { method: 'POST', body: { userId: user.id } })).status;
    });
    if (status) setState(status === 'friends' || status === 'already_friends' ? 'friend' : 'outgoing');
  };
  return (
    <Panel className="friend-row">
      <Avatar id={user.id} name={user.name} photoUrl={user.photoUrl} />
      <div className="friend-row__body">
        <strong>{user.name}</strong>
        {hint ? <span className="app-muted">{hint}</span> : <RatingBadge rating={user.rating} showValue={false} />}
      </div>
      {state === 'none' ? (
        <Button size="sm" icon="plus" onClick={() => void add()}>
          Добавить
        </Button>
      ) : (
        <Badge tone={state === 'friend' ? 'green' : 'muted'}>{RELATION_LABEL[state]}</Badge>
      )}
    </Panel>
  );
}
