import { Avatar, Badge, Balance, Button, Icon, Panel, PlayingCard, ProgressBar, Tile, type TileProps } from '@arena/ui';
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
  const { setTab, push } = useNav();
  const s = me.stats;

  return (
    <div className="app-stack">
      <Panel className="home-profile" onClick={() => push('profile')} role="button" tabIndex={0}>
        <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={58} ring="violet" />
        <div className="home-profile__main">
          <div className="home-profile__name">
            <strong>{me.name}</strong>
            <Badge tone="violet">Ур. {s.level}</Badge>
          </div>
          <ProgressBar value={s.xp} max={s.xp + s.xpToNext} />
          <div className="home-profile__meta">
            <span><Icon name="star" size={14} /> {s.rating}</span>
            <span><Icon name="trophy" size={14} /> {s.gamesWon} побед</span>
            <span>{s.winRate}%</span>
          </div>
        </div>
      </Panel>

      <div className="home-wallet">
        <Panel padded={false} className="home-wallet__main">
          <span className="home-wallet__label">Баланс</span>
          <Balance kind="chips" value={me.wallet.chips} />
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
        <Button size="lg" variant="gold" icon="play" block onClick={() => setTab('games')}>
          Играть
        </Button>
      </section>

      <div className="home-grid">
        {LINKS.map((link) => (
          <Tile
            key={link.title}
            {...link}
            badge={link.title === 'Достижения' ? <Badge tone="gold">{s.achievementsUnlocked}/{s.achievementsTotal}</Badge> : undefined}
            onClick={() => ('tab' in link ? setTab(link.tab) : push(link.page))}
          />
        ))}
      </div>
    </div>
  );
}
