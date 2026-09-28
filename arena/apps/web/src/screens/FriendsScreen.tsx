import type { FriendDto, FriendRequestsDto, RecentPlayerDto, Relation, SearchUserDto, SendRequestResult } from '@arena/shared';
import { Avatar, Badge, BottomSheet, Button, EmptyState, Icon, RatingBadge, Tabs } from '@arena/ui';
import { ratingBadge } from '@arena/shared';
import { tg } from '../lib/telegram.js';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useRealtime } from '../realtime.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';


export default function FriendsScreen() {
  const { requestCount } = useRealtime();
  const [tab, setTab] = useState<'friends' | 'requests' | 'recent'>(requestCount ? 'requests' : 'friends');
  const [searching, setSearching] = useState(false);
  return (
    <div className="app-stack people">
      <ScreenHeader
        title="Друзья"
        action={
          <button type="button" className="app-bar__icon" aria-label="Найти игрока" aria-pressed={searching} onClick={() => setSearching((v) => !v)}>
            <Icon name="search" size={22} />
          </button>
        }
      />
      {searching && <SearchBox />}
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

const PRESENCE_TEXT = { online: 'в сети', in_game: 'в игре', offline: 'не в сети' } as const;

/** Square portrait with the league mark in the corner, as at the table. */
function PeopleAvatar({ user }: { user: { id: string; name: string; photoUrl: string | null; rating: number } }) {
  const badge = ratingBadge(user.rating);
  return (
    <span className="people-avatar" style={{ ['--league' as string]: badge.league.color }}>
      <Avatar id={user.id} name={user.name} photoUrl={user.photoUrl} size={56} />
      <span className="people-avatar__level">{badge.level}</span>
    </span>
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
  const [removing, setRemoving] = useState<FriendDto | null>(null);
  const inRoom = room?.status === 'waiting';
  const invite = (f: FriendDto) => act(() => api(`/friends/${f.id}/invite`, { method: 'POST' }), `${f.name} получит приглашение`);
  const write = (f: FriendDto) => {
    if (!f.username) return;
    const url = `https://t.me/${f.username}`;
    if (tg) tg.openTelegramLink(url);
    else window.open(url, '_blank', 'noopener');
  };

  const remove = async (f: FriendDto) => {
    if (await act(() => api(`/friends/${f.id}`, { method: 'DELETE' }), `${f.name} удалён из друзей`)) query.reload();
  };

  return (
    <>
      <QueryView query={query}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState icon="users" title="Пока никого" text="Найдите друга по @username или добавьте соперника из «Недавних»." />
          ) : (
            <div className="people-list">
              {list.map((f) => (
                <div key={f.id} className="people-row">
                  <button type="button" className="people-row__who" onClick={() => setPicked(f)}>
                    <PeopleAvatar user={f} />
                    <span className="people-row__text">
                      <strong>{f.name}</strong>
                      <span className={`people-row__sub people-row__sub--${f.presence}`}>{f.username ? `@${f.username} · ` : ''}{PRESENCE_TEXT[f.presence]}</span>
                    </span>
                  </button>
                  <button type="button" className="people-row__btn" aria-label={`Удалить ${f.name} из друзей`} onClick={() => setRemoving(f)}>
                    <Icon name="close" size={20} />
                  </button>
                  <button
                    type="button"
                    className="people-row__btn"
                    aria-label={inRoom ? `Позвать ${f.name} за стол` : `Написать ${f.name}`}
                    disabled={!inRoom && !f.username}
                    onClick={() => (inRoom ? void invite(f) : write(f))}
                  >
                    <Icon name="mail" size={20} />
                  </button>
                </div>
              ))}
            </div>
          )
        }
      </QueryView>

      <BottomSheet open={removing !== null} title="Удалить из друзей?" onClose={() => setRemoving(null)}>
        {removing && (
          <div className="app-stack">
            <p className="app-muted">{removing.name} пропадёт из списка. Снова добавить можно в «Недавних» или через поиск.</p>
            <Button block variant="danger" onClick={() => void remove(removing).then(() => setRemoving(null))}>
              Удалить
            </Button>
          </div>
        )}
      </BottomSheet>

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
          <div className="people-list">
            {incoming.map((r) => (
              <div key={r.id} className="people-row people-row--plain">
                <PeopleAvatar user={r.user} />
                <div className="people-row__text">
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
              </div>
            ))}
            {outgoing.length > 0 && <h3 className="app-section">Вы отправили</h3>}
            {outgoing.map((r) => (
              <div key={r.id} className="people-row people-row--plain">
                <PeopleAvatar user={r.user} />
                <div className="people-row__text">
                  <strong>{r.user.name}</strong>
                  <span className="app-muted">ждём ответа</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => void act(() => api(`/friends/requests/${r.id}`, { method: 'DELETE' })).then(reload)}>
                  Отменить
                </Button>
              </div>
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
          <div className="people-list">
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
    <div className="people-row people-row--plain">
      <PeopleAvatar user={user} />
      <div className="people-row__text">
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
    </div>
  );
}
