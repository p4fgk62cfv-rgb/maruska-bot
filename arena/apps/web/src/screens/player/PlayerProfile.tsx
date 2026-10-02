import { formatStake, ratingBadge, type MatchDto, type PlayerProfileDto, type ProfileAchievementDto, type SendRequestResult } from '@arena/shared';
import { Avatar, Button, EmptyState, Icon, RatingBadge, Skeleton, formatCompact } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ACHIEVEMENT_ICON } from '../../lib/achievements.js';
import { ApiError, api } from '../../lib/api.js';
import { ringOf } from '../../lib/cosmetics.js';
import { modeText, plural, presenceText, whenText } from '../../lib/people.js';
import { tg } from '../../lib/telegram.js';
import { useQuery } from '../../lib/useQuery.js';
import { useRealtime } from '../../realtime.js';
import { useToast } from '../../toast.js';
import { ChallengeSheet } from './Challenge.js';

const OUTCOME_RU = { win: 'Победа', loss: 'Дурак', draw: 'Ничья', left: 'Сдача' } as const;
const TIER_RU = { common: 'Обычное', rare: 'Редкое', epic: 'Эпическое', legendary: 'Легендарное' } as const;

/**
 * The game card of a player — mine on «Профиль», anyone else's from friends, the lobby or
 * the result screen. `atTable`: opened during a game, so no «Позвать в игру».
 */
export function PlayerProfileView({
  userId,
  atTable = false,
  onOpenPlayer,
  onAchievements,
}: {
  userId: string;
  atTable?: boolean;
  /** Tap on an opponent in the history. */
  onOpenPlayer?: (userId: string) => void;
  onAchievements?: () => void;
}) {
  const query = useQuery<PlayerProfileDto>(`/players/${userId}/profile`);
  const { presence: live } = useRealtime();
  const [card, setCard] = useState<PlayerProfileDto | null>(null);
  useEffect(() => setCard(query.data ?? null), [query.data]);

  if (!card) {
    if (query.error) {
      return <EmptyState icon="close" title="Не удалось загрузить" text={query.error.message} action={<Button size="sm" onClick={query.reload}>Повторить</Button>} />;
    }
    return (
      <div className="pcard" aria-busy="true">
        <Skeleton height={250} radius={24} />
        <Skeleton height={140} radius={20} />
        <Skeleton height={200} radius={20} />
      </div>
    );
  }
  const presence = live[card.id] ?? card.presence;
  return (
    <div className="pcard" style={{ ['--league' as string]: ratingBadge(card.rating).league.color }}>
      <Hero card={card} presence={presence} atTable={atTable} onChange={setCard} />
      <Overview card={card} />
      {card.form.length > 0 && <Form form={card.form} />}
      {card.modes.length > 0 && <Modes modes={card.modes} />}
      {card.together && <Together card={card} onOpenPlayer={onOpenPlayer} />}
      <Achievements card={card} onAchievements={onAchievements} />
      <History userId={card.id} first={card.recent} onOpenPlayer={onOpenPlayer} />
    </div>
  );
}

function Hero({ card, presence, atTable, onChange }: { card: PlayerProfileDto; presence: PlayerProfileDto['presence']; atTable: boolean; onChange: (c: PlayerProfileDto) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [challenge, setChallenge] = useState(false);
  const [watching, setWatching] = useState(false);
  const [removing, setRemoving] = useState(false);
  const self = card.relation === 'self';

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(null);
    }
  };
  const addFriend = () =>
    run('friend', async () => {
      const { status } = await api<SendRequestResult>('/friends/requests', { method: 'POST', body: { userId: card.id } });
      const relation = status === 'friends' || status === 'already_friends' ? 'friend' : 'outgoing';
      onChange({ ...card, relation });
      toast(relation === 'friend' ? 'Теперь вы друзья' : 'Заявка отправлена', 'success');
    });
  const toggleFavorite = () =>
    run('favorite', async () => {
      const { favorite } = await api<{ favorite: boolean }>(`/players/${card.id}/favorite`, { method: card.favorite ? 'DELETE' : 'PUT' });
      onChange({ ...card, favorite });
      toast(favorite ? 'Добавлен(а) в избранные' : 'Убран(а) из избранных', 'success');
    });
  const watch = () =>
    run('watch', async () => {
      const r = await api<{ watching: boolean }>(`/friends/${card.id}/watch`, { method: watching ? 'DELETE' : 'POST' });
      setWatching(r.watching);
      if (r.watching) toast('Сообщим, когда партия закончится', 'success');
    });
  const removeFriend = () =>
    run('remove', async () => {
      await api(`/friends/${card.id}`, { method: 'DELETE' });
      onChange({ ...card, relation: 'none' });
      setRemoving(false);
      toast(`${card.name} больше не в друзьях`, 'success');
    });
  const write = () => {
    if (!card.username) return;
    const url = `https://t.me/${card.username}`;
    if (tg) tg.openTelegramLink(url);
    else window.open(url, '_blank', 'noopener');
  };
  const canWatch = (card.relation === 'friend' || card.favorite) && presence === 'in_game';

  return (
    <section className="pcard__hero">
      <div className="pcard__glow" aria-hidden="true" />
      <div className="pcard__portrait">
        <Avatar id={card.id} name={card.name} photoUrl={card.photoUrl} size={96} ring={card.frame ? ringOf(card.frame) : 'gold'} crown={Boolean(card.crown)} status={self ? undefined : presence} />
        <span className="pcard__level">{ratingBadge(card.rating).level}</span>
      </div>
      <h2 className="pcard__name">
        {card.name}
        {card.premium && <Icon name="crown" size={18} />}
      </h2>
      {card.title && (
        <span className={`pcard__title pcard__title--${card.title.tier}`}>
          <Icon name={ACHIEVEMENT_ICON[card.title.icon] ?? 'star'} size={14} /> {card.title.title}
        </span>
      )}
      <span className="pcard__sub">
        {card.username && <span>@{card.username}</span>}
        {!self && <span className={`pcard__presence pcard__presence--${presence}`}>{presenceText(presence, card.lastSeenAt)}</span>}
      </span>
      <RatingBadge rating={card.rating} />
      {card.season && (
        <span className="pcard__season">
          {card.season.title}: {card.season.rating.toLocaleString('ru-RU')} рейтинга · {card.season.wins} {plural(card.season.wins, 'победа', 'победы', 'побед')}
        </span>
      )}

      {!self && (
        <div className="pcard__actions">
          {card.relation === 'none' ? (
            <Button size="sm" icon="userPlus" loading={busy === 'friend'} onClick={() => void addFriend()}>В друзья</Button>
          ) : (
            <span className={`pcard__chip${card.relation === 'friend' ? ' pcard__chip--friend' : ''}`}>
              {card.relation === 'friend' ? '✓ Друг' : card.relation === 'incoming' ? 'Ждёт ответа' : 'Заявка отправлена'}
            </span>
          )}
          <button
            type="button"
            className={`pcard__icon${card.favorite ? ' pcard__icon--on' : ''}`}
            aria-pressed={card.favorite}
            aria-label={card.favorite ? 'Убрать из избранных' : 'В избранные'}
            disabled={busy === 'favorite'}
            onClick={() => void toggleFavorite()}
          >
            <Icon name="star" size={20} />
          </button>
          {canWatch && (
            <button
              type="button"
              className={`pcard__icon${watching ? ' pcard__icon--on' : ''}`}
              aria-pressed={watching}
              aria-label="Сообщить, когда освободится"
              disabled={busy === 'watch'}
              onClick={() => void watch()}
            >
              <Icon name={watching ? 'bellOn' : 'bell'} size={20} />
            </button>
          )}
          {card.username && !atTable && (
            <button type="button" className="pcard__icon" aria-label="Написать в Telegram" onClick={write}>
              <Icon name="mail" size={20} />
            </button>
          )}
          {card.relation === 'friend' && !atTable && (
            <Button size="sm" variant="gold" icon="play" onClick={() => setChallenge(true)}>
              Позвать
            </Button>
          )}
        </div>
      )}
      {card.relation === 'friend' && !atTable && (
        <button type="button" className={`pcard__remove${removing ? ' pcard__remove--sure' : ''}`} disabled={busy === 'remove'} onClick={() => (removing ? void removeFriend() : setRemoving(true))}>
          {removing ? 'Нажмите ещё раз, чтобы удалить из друзей' : 'Удалить из друзей'}
        </button>
      )}
      {!atTable && <ChallengeSheet friend={challenge ? card : null} onClose={() => setChallenge(false)} />}
    </section>
  );
}

/** Win rate as a ring, the numbers around it as tiles. */
function Overview({ card }: { card: PlayerProfileDto }) {
  const s = card.stats;
  const r = 34;
  const c = 2 * Math.PI * r;
  const tiles = [
    { label: 'Сыграно', value: s.games.toLocaleString('ru-RU') },
    { label: 'Побед', value: s.wins.toLocaleString('ru-RU') },
    { label: 'Поражений', value: s.losses.toLocaleString('ru-RU') },
    { label: 'Серия', value: s.streak ? `🔥 ${s.streak}` : '0' },
    { label: 'Лучшая серия', value: String(s.bestStreak) },
    { label: 'Выиграно', value: formatCompact(s.winnings) },
  ];
  return (
    <section className="pcard__panel pcard__overview">
      <div className="pcard__ring" role="img" aria-label={`Процент побед ${s.winRate}%`}>
        <svg viewBox="0 0 80 80" aria-hidden="true">
          <circle cx="40" cy="40" r={r} className="pcard__ring-bg" />
          <circle cx="40" cy="40" r={r} className="pcard__ring-fg" strokeDasharray={`${(s.winRate / 100) * c} ${c}`} />
        </svg>
        <strong>{s.winRate}%</strong>
        <span>побед</span>
      </div>
      <div className="pcard__tiles">
        {tiles.map((t) => (
          <div key={t.label} className="pcard__tile">
            <strong>{t.value}</strong>
            <span>{t.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Form({ form }: { form: PlayerProfileDto['form'] }) {
  return (
    <section className="pcard__panel pcard__form">
      <h3>Последние партии</h3>
      <div className="pcard__dots">
        {form.map((f, i) => (
          <span key={i} className={`pcard__dot pcard__dot--${f}`} title={f === 'W' ? 'Победа' : f === 'D' ? 'Ничья' : 'Поражение'}>
            {f === 'W' ? 'В' : f === 'D' ? 'Н' : 'П'}
          </span>
        ))}
      </div>
    </section>
  );
}

function Modes({ modes }: { modes: PlayerProfileDto['modes'] }) {
  const [top, ...rest] = modes;
  return (
    <section className="pcard__panel">
      <h3>Любимый тип игры</h3>
      <div className="pcard__fav">
        <Icon name={top!.variant === 'perevodnoy' ? 'modePerevodnoy' : 'modePodkidnoy'} size={30} />
        <div>
          <strong>{modeText(top!)}</strong>
          <span>
            {top!.share}% партий · побед {top!.games ? Math.round((top!.wins / top!.games) * 100) : 0}%
          </span>
        </div>
      </div>
      {rest.length > 0 && (
        <div className="pcard__bars">
          {rest.map((m) => (
            <div key={`${m.variant}${m.deckSize}${m.players}`} className="pcard__bar">
              <span>{modeText(m)}</span>
              <i style={{ width: `${Math.max(4, m.share)}%` }} />
              <small>{m.share}%</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Together({ card, onOpenPlayer }: { card: PlayerProfileDto; onOpenPlayer?: (id: string) => void }) {
  const t = card.together!;
  if (!t.games) {
    return (
      <section className="pcard__panel">
        <h3>Совместные партии</h3>
        <p className="app-muted">Вы ещё не играли за одним столом.</p>
      </section>
    );
  }
  const total = Math.max(1, t.myWins + t.theirWins);
  return (
    <section className="pcard__panel">
      <h3>
        Совместные партии <small>{t.games}</small>
      </h3>
      <div className="pcard__score">
        <span>Вы</span>
        <strong>
          {t.myWins} : {t.theirWins}
        </strong>
        <span>{card.name}</span>
      </div>
      <div className="pcard__duel" aria-hidden="true">
        <i style={{ width: `${(t.myWins / total) * 100}%` }} />
      </div>
      {t.draws > 0 && <p className="app-muted">Без победителя между вами: {t.draws}</p>}
      <div className="pcard__matches">
        {t.recent.slice(0, 5).map((m) => (
          <MatchRow key={m.gameId} match={m} onOpenPlayer={onOpenPlayer} />
        ))}
      </div>
    </section>
  );
}

function Achievements({ card, onAchievements }: { card: PlayerProfileDto; onAchievements?: () => void }) {
  const [open, setOpen] = useState<ProfileAchievementDto | null>(null);
  const rare = card.achievements.filter((a) => a.tier !== 'common');
  return (
    <section className="pcard__panel">
      <h3>
        Достижения <small>{card.achievements.length} / {card.achievementsTotal}</small>
        {onAchievements && (
          <button type="button" className="pcard__link" onClick={onAchievements}>
            Все
          </button>
        )}
      </h3>
      {card.achievements.length === 0 ? (
        <p className="app-muted">Пока ни одного — всё впереди.</p>
      ) : (
        <>
          {rare.length > 0 && (
            <div className="pcard__titles">
              {rare.slice(0, 4).map((a) => (
                <button key={a.key} type="button" className={`pcard__rare pcard__rare--${a.tier}`} onClick={() => setOpen(open?.key === a.key ? null : a)}>
                  <Icon name={ACHIEVEMENT_ICON[a.icon] ?? 'star'} size={20} />
                  <span>
                    <strong>{a.title}</strong>
                    <small>
                      {TIER_RU[a.tier]} · есть у {a.rarity.toLocaleString('ru-RU')}% игроков
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
          <div className="pcard__badges">
            {card.achievements.map((a) => (
              <button key={a.key} type="button" className={`pcard__badge pcard__badge--${a.tier}`} aria-label={a.title} onClick={() => setOpen(open?.key === a.key ? null : a)}>
                <Icon name={ACHIEVEMENT_ICON[a.icon] ?? 'star'} size={20} />
              </button>
            ))}
          </div>
          {open && (
            <p className="pcard__about">
              <strong>{open.title}</strong> — {open.description}. {TIER_RU[open.tier]}: есть у {open.rarity.toLocaleString('ru-RU')}% игроков.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function History({ userId, first, onOpenPlayer }: { userId: string; first: MatchDto[]; onOpenPlayer?: (id: string) => void }) {
  const [list, setList] = useState(first);
  const [more, setMore] = useState(first.length >= 10);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setList(first);
    setMore(first.length >= 10);
  }, [first]);
  const loadMore = async () => {
    setBusy(true);
    try {
      const next = await api<MatchDto[]>(`/players/${userId}/matches?limit=20&before=${encodeURIComponent(list[list.length - 1]!.at)}`);
      setList([...list, ...next]);
      setMore(next.length === 20);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="pcard__panel">
      <h3>История матчей</h3>
      {list.length === 0 ? (
        <p className="app-muted">Сыгранных партий пока нет.</p>
      ) : (
        <div className="pcard__matches">
          {list.map((m) => (
            <MatchRow key={m.gameId} match={m} onOpenPlayer={onOpenPlayer} />
          ))}
        </div>
      )}
      {more && (
        <Button block size="sm" variant="ghost" loading={busy} onClick={() => void loadMore()}>
          Показать ещё
        </Button>
      )}
    </section>
  );
}

function MatchRow({ match, onOpenPlayer }: { match: MatchDto; onOpenPlayer?: (id: string) => void }) {
  const minutes = match.durationMs ? Math.max(1, Math.round(match.durationMs / 60_000)) : null;
  return (
    <div className={`match match--${match.outcome}`}>
      <span className="match__mark" />
      <div className="match__main">
        <strong>
          {OUTCOME_RU[match.outcome]}
          {match.place && match.mode.players > 2 && match.outcome === 'win' ? ` · ${match.place} место` : ''}
        </strong>
        <span>
          {whenText(match.at)}
          {minutes ? ` · ${minutes} мин` : ''}
        </span>
        <span>{modeText(match.mode)}</span>
      </div>
      <div className="match__people">
        {match.opponents.slice(0, 3).map((o) => (
          <button key={o.id} type="button" className="match__opp" aria-label={o.name} disabled={!onOpenPlayer} onClick={() => onOpenPlayer?.(o.id)}>
            <Avatar id={o.id} name={o.name} photoUrl={o.photoUrl} size={26} />
          </button>
        ))}
      </div>
      <div className="match__money">
        <strong className={match.net >= 0 ? 'tx-plus' : 'tx-minus'}>
          {match.net > 0 ? '+' : match.net < 0 ? '−' : ''}
          {formatStake(Math.abs(match.net))}
        </strong>
        <span>ставка {formatStake(match.stake)}</span>
      </div>
    </div>
  );
}
