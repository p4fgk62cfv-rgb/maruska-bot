import type { FavoriteDto, FriendDto, Presence, FriendRequestsDto, RecentPlayerDto, Relation, SearchUserDto, SendRequestResult } from '@arena/shared';
import { Avatar, Badge, Button, EmptyState, Icon, RatingBadge, Tabs } from '@arena/ui';
import { ratingBadge } from '@arena/shared';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useRealtime } from '../realtime.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';
import { presenceText } from '../lib/people.js';
import { useNav } from '../navigation.js';
import { ChallengeSheet } from './player/Challenge.js';


export default function FriendsScreen() {
  const { requestCount } = useRealtime();
  const [tab, setTab] = useState<'friends' | 'mutual' | 'requests' | 'recent'>(requestCount ? 'requests' : 'friends');
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
          { value: 'mutual', label: 'Друзья друзей' },
          { value: 'requests', label: requestCount ? `Заявки · ${requestCount}` : 'Заявки' },
          { value: 'recent', label: 'Недавние' },
        ]}
      />
      {tab === 'friends' && <FriendsTab />}
      {tab === 'mutual' && <FriendsOfFriendsTab />}
      {tab === 'requests' && <RequestsTab />}
      {tab === 'recent' && <RecentTab />}
    </div>
  );
}

/** Square portrait with the league mark in the corner, as at the table. */
function PeopleAvatar({ user, presence }: { user: { id: string; name: string; photoUrl: string | null; rating: number }; presence?: Presence }) {
  const badge = ratingBadge(user.rating);
  return (
    <span className="people-avatar" style={{ ['--league' as string]: badge.league.color }}>
      <Avatar id={user.id} name={user.name} photoUrl={user.photoUrl} size={56} status={presence} />
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
  const favoritesQuery = useQuery<FavoriteDto[]>('/friends/favorites');
  const { presence: live } = useRealtime();
  const { openPlayer } = useNav();
  const act = useAction();
  const [challenge, setChallenge] = useState<FriendDto | null>(null);
  const [flags, setFlags] = useState<Record<string, { favorite?: boolean; watching?: boolean }>>({});

  const view = (f: FriendDto): FriendDto => ({ ...f, presence: live[f.id] ?? f.presence, ...flags[f.id] });
  const toggleFavorite = (f: FriendDto) =>
    act(async () => {
      const { favorite } = await api<{ favorite: boolean }>(`/players/${f.id}/favorite`, { method: f.favorite ? 'DELETE' : 'PUT' });
      setFlags((m) => ({ ...m, [f.id]: { ...m[f.id], favorite } }));
      favoritesQuery.reload();
    });
  const toggleWatch = (f: FriendDto) =>
    act(async () => {
      const { watching } = await api<{ watching: boolean }>(`/friends/${f.id}/watch`, { method: f.watching ? 'DELETE' : 'POST' });
      setFlags((m) => ({ ...m, [f.id]: { ...m[f.id], watching } }));
    }, f.watching ? undefined : `Сообщим, когда ${f.name} закончит партию`);

  const row = (f: FriendDto, friend: boolean) => (
    <div key={f.id} className={`people-row${f.presence === 'offline' ? '' : ' people-row--live'}`}>
      <button type="button" className="people-row__who" onClick={() => openPlayer(f.id)}>
        <PeopleAvatar user={f} presence={f.presence} />
        <span className="people-row__text">
          <strong>{f.name}</strong>
          {f.username && <span className="people-row__sub">@{f.username}</span>}
          <span className={`people-row__sub people-row__sub--${f.presence}`}>{presenceText(f.presence, f.lastSeenAt)}</span>
        </span>
      </button>
      <button type="button" className={`people-row__btn${f.favorite ? ' people-row__btn--on' : ''}`} aria-pressed={f.favorite} aria-label={f.favorite ? `Убрать ${f.name} из избранных` : `${f.name} в избранные`} onClick={() => void toggleFavorite(f)}>
        <Icon name="star" size={20} />
      </button>
      {f.presence === 'in_game' ? (
        <button type="button" className={`people-row__btn${f.watching ? ' people-row__btn--on' : ''}`} aria-pressed={f.watching} aria-label={`Сообщить, когда ${f.name} освободится`} onClick={() => void toggleWatch(f)}>
          <Icon name={f.watching ? 'bellOn' : 'bell'} size={20} />
        </button>
      ) : friend ? (
        <button type="button" className="people-row__btn people-row__btn--play" aria-label={`Позвать ${f.name} в игру`} onClick={() => setChallenge(f)}>
          <Icon name="play" size={20} />
        </button>
      ) : (
        <span className="people-row__btn" aria-hidden="true" />
      )}
    </div>
  );

  return (
    <>
      <QueryView query={query}>
        {(raw) => {
          const friends = raw.map(view);
          const friendIds = new Set(friends.map((f) => f.id));
          const favorites = (favoritesQuery.data ?? []).map(view).filter((f) => f.favorite !== false);
          const rest = friends.filter((f) => !favorites.some((x) => x.id === f.id) && !f.favorite);
          const online = friends.filter((f) => f.presence !== 'offline').length;
          if (!friends.length && !favorites.length) {
            return <EmptyState icon="users" title="Пока никого" text="Найдите друга по @username или добавьте соперника из «Недавних»." />;
          }
          return (
            <div className="people-list">
              {favorites.length > 0 && (
                <>
                  <h3 className="people-list__head">
                    <Icon name="star" size={16} /> Избранные
                  </h3>
                  {favorites.map((f) => row(f, friendIds.has(f.id)))}
                </>
              )}
              {rest.length > 0 && (
                <h3 className="people-list__head">
                  Друзья <small>{online ? `${online} в сети из ${friends.length}` : friends.length}</small>
                </h3>
              )}
              {rest.map((f) => row(f, true))}
            </div>
          );
        }}
      </QueryView>
      <ChallengeSheet friend={challenge} onClose={() => setChallenge(null)} />
    </>
  );
}

type FriendOfFriendDto = { id: string; name: string; username: string | null; photoUrl: string | null; rating: number; mutualFriends: string[]; relation: Relation };

function FriendsOfFriendsTab() {
  const query = useQuery<FriendOfFriendDto[]>('/friends/of-friends');
  return (
    <QueryView query={query}>
      {(list) => list.length === 0 ? (
        <EmptyState icon="users" title="Пока никого" text="Здесь появятся игроки, которые дружат с твоими друзьями." />
      ) : (
        <div className="people-list">
          {list.map((person) => (
            <PersonRow
              key={person.id}
              user={person}
              relation={person.relation}
              hint={person.mutualFriends.length === 1
                ? `Общий друг: ${person.mutualFriends[0]}`
                : `Общие друзья: ${person.mutualFriends.slice(0, 3).join(', ')}${person.mutualFriends.length > 3 ? ` и ещё ${person.mutualFriends.length - 3}` : ''}`}
            />
          ))}
        </div>
      )}
    </QueryView>
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
  const { openPlayer } = useNav();
  const add = async () => {
    let status: SendRequestResult['status'] | null = null;
    await act(async () => {
      status = (await api<SendRequestResult>('/friends/requests', { method: 'POST', body: { userId: user.id } })).status;
    });
    if (status) setState(status === 'friends' || status === 'already_friends' ? 'friend' : 'outgoing');
  };
  return (
    <div className="people-row people-row--plain">
      <button type="button" className="people-row__who" onClick={() => openPlayer(user.id)}>
        <PeopleAvatar user={user} />
        <span className="people-row__text">
          <strong>{user.name}</strong>
          {hint ? <span className="app-muted">{hint}</span> : <RatingBadge rating={user.rating} showValue={false} />}
        </span>
      </button>
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
