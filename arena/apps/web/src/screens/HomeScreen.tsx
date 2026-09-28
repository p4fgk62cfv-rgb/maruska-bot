import { Avatar, Badge, Balance, Button, Icon, Panel, PlayingCard, RatingBadge, Tile, type TileProps } from '@arena/ui';
import { DAILY_CREDITS, type MyRoomDto } from '@arena/shared';
import { useRealtime } from '../realtime.js';
import { ringOf } from '../lib/cosmetics.js';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { haptic } from '../lib/telegram.js';
import { useSession } from '../session.js';
import { useToast } from '../toast.js';
import { useNav, type Page, type Tab } from '../navigation.js';
import { useMe } from '../session.js';

type Link = Omit<TileProps, 'onClick'> & ({ tab: Tab } | { page: Page });

const LINKS: Link[] = [
  { icon: 'cards', title: 'Открытые игры', hint: 'Лобби комнат', tone: 'violet', tab: 'games' },
  { icon: 'lock', title: 'Приватные игры', hint: 'По ссылке и паролю', tone: 'cyan', tab: 'games' },
  { icon: 'trophy', title: 'Турниры', hint: 'Призовые фонды', tone: 'gold', tab: 'tournaments' },
  { icon: 'users', title: 'Друзья', hint: 'Играйте вместе', tone: 'green', tab: 'friends' },
  { icon: 'bag', title: 'Предметы', hint: 'Рубашки, столы, рамки', tone: 'rose', page: 'items' },
  { icon: 'star', title: 'Достижения', tone: 'gold', page: 'achievements' },
  { icon: 'news', title: 'Новости', hint: 'Что нового', tone: 'cyan', page: 'news' },
  { icon: 'medal', title: 'Доска почёта', hint: 'Лучшие игроки', tone: 'gold', page: 'leaderboard' },
  { icon: 'settings', title: 'Настройки', tone: 'violet', page: 'settings' },
  { icon: 'book', title: 'Правила', hint: 'Как играть в дурака', tone: 'green', page: 'rules' },
];

export function HomeScreen() {
  const me = useMe();
  const { refreshMe } = useSession();
  const toast = useToast();
  const { setTab, push } = useNav();
  const [claiming, setClaiming] = useState(false);
  const [finding, setFinding] = useState(false);
  const { enterRoom } = useRealtime();

  const quickGame = () => {
    setFinding(true);
    api<MyRoomDto>('/rooms/quick', { method: 'POST', body: {} })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setFinding(false));
  };
  const s = me.stats;

  const claimDaily = () => {
    setClaiming(true);
    api('/wallet/daily-credits', { method: 'POST' })
      .then(() => {
        haptic.success();
        toast(`+${DAILY_CREDITS.amount} кредитов`, 'success');
        return refreshMe();
      })
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setClaiming(false));
  };

  return (
    <div className="app-stack">
      <Panel className="home-profile" onClick={() => push('profile')} role="button" tabIndex={0}>
        <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={58} ring={me.equipped.frame ? ringOf(me.equipped.frame) : 'violet'} crown={Boolean(me.equipped.crown)} />
        <div className="home-profile__main">
          <div className="home-profile__name">
            <strong>{me.name}</strong>
            {me.premiumUntil && new Date(me.premiumUntil) > new Date() && <Badge tone="gold">Премиум</Badge>}
          </div>
          <RatingBadge rating={s.rating} streak={me.bonus.streak} />
          <div className="home-profile__meta">
            <span><Icon name="trophy" size={14} /> {s.gamesWon} побед</span>
            <span>{s.winRate}%</span>
            {me.bonus.availableAt === null && <span className="home-profile__bonus">×{me.bonus.multiplier} к рейтингу</span>}
          </div>
        </div>
      </Panel>

      <div className="home-wallet">
        <Panel padded={false} className="home-wallet__main">
          <span className="home-wallet__label">Кредиты</span>
          <Balance kind="credits" value={me.wallet.credits} />
          {me.dailyCredits.available && (
            <Button size="sm" variant="gold" loading={claiming} onClick={claimDaily}>
              +{DAILY_CREDITS.amount} бесплатно
            </Button>
          )}
        </Panel>
        <Panel padded={false} className="home-wallet__side">
          <Balance kind="coins" value={me.wallet.coins} compact />
          <Balance kind="diamonds" value={me.wallet.diamonds} compact />
        </Panel>
      </div>

      <section className="home-hero" aria-label="Быстрая игра">
        <div className="home-hero__felt" />
        <div className="home-hero__cards" aria-hidden="true">
          <PlayingCard card="AS" width={54} />
          <PlayingCard card="KH" width={54} />
          <PlayingCard card="QD" width={54} trump />
          <PlayingCard faceDown width={54} />
        </div>
        <div className="home-hero__text">
          <span className="home-hero__kicker">Дурак онлайн</span>
          <h2>Быстрая игра</h2>
          <p>Подберём стол по вашей ставке</p>
        </div>
        <Button size="lg" variant="gold" icon="play" block loading={finding} onClick={quickGame}>
          Играть
        </Button>
      </section>

      <div className="home-grid">
        {LINKS.map((link) => (
          <Tile
            key={link.title}
            {...link}
            // The count goes under the title: a badge beside it squeezes «Достижения» into two lines on phones.
            hint={'page' in link && link.page === 'achievements' ? `Открыто ${s.achievementsUnlocked} из ${s.achievementsTotal}` : link.hint}
            onClick={() => ('tab' in link ? setTab(link.tab) : push(link.page))}
          />
        ))}
      </div>
    </div>
  );
}
