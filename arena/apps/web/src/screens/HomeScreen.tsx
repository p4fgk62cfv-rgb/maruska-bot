import { Avatar, Balance, Icon, RatingBadge, type IconName } from '@arena/ui';
import { DAILY_CREDITS, type MyRoomDto } from '@arena/shared';
import { useState } from 'react';
import { ringOf } from '../lib/cosmetics.js';
import { useSettings } from '../lib/settings.js';
import { ApiError, api } from '../lib/api.js';
import { haptic } from '../lib/telegram.js';
import { useNav, type Page } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { InstallCard } from './InstallCard.js';
import { NEWS, newsDate, useUnseenNews } from '../lib/news.js';
import { chatHasNew } from '../lib/chat.js';

interface Tile {
  icon: IconName;
  title: string;
  page?: Page;
}

const TILES: Tile[] = [
  { icon: 'gift', title: 'Задания', page: 'daily' },
  { icon: 'chat', title: 'Чат', page: 'chat' },
  { icon: 'trophy', title: 'Турниры', page: 'tournaments' },
  { icon: 'news', title: 'Новости', page: 'news' },
  { icon: 'users', title: 'Друзья', page: 'friends' },
  { icon: 'bag', title: 'Предметы', page: 'items' },
  { icon: 'crown', title: 'Доска почёта', page: 'leaderboard' },
  { icon: 'star', title: 'Достижения', page: 'achievements' },
  { icon: 'settings', title: 'Настройки', page: 'settings' },
  { icon: 'share', title: 'Пригласить', page: 'invite' },
  { icon: 'book', title: 'Правила', page: 'rules' },
  { icon: 'server', title: 'Серверы', page: 'servers' },
];

export function HomeScreen() {
  const me = useMe();
  const homeDesign = useSettings().homeDesign;
  const { push } = useNav();
  const toast = useToast();
  const { enterRoom, requestCount } = useRealtime();
  const [finding, setFinding] = useState(false);
  const unseenNews = useUnseenNews();
  const latest = NEWS[0]!;
  const s = me.stats;

  const quickGame = () => {
    setFinding(true);
    api<MyRoomDto>('/rooms/quick', { method: 'POST', body: {} })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setFinding(false));
  };

  const counter = (tile: Tile): string | number | null => {
    if (tile.page === 'achievements') return `${s.achievementsUnlocked} / ${s.achievementsTotal}`;
    if (tile.page === 'friends' && requestCount) return requestCount;
    if (tile.page === 'news' && unseenNews) return unseenNews;
    if (tile.page === 'daily' && me.daily.claimable) return me.daily.claimable;
    if (tile.page === 'chat' && chatHasNew(me.chatLastAt)) return 'новое';
    return null;
  };

  return (
    <div className={`home${homeDesign === 'daylight' ? ' home--premium' : ''}${homeDesign === 'vegas' ? ' home--vegas' : ''}`}>
      <HomeBar />

      {(homeDesign === 'daylight' || homeDesign === 'vegas') && (
      <section className="arena-hero" aria-label="Маруська Арена">
        <div className="arena-hero__ornament" aria-hidden="true">
          <span className="arena-card arena-card--left">A<span>♥</span></span>
          <span className="arena-card arena-card--back">✦</span>
          <span className="arena-card arena-card--right">K<span>♠</span></span>
        </div>
        <p className="arena-hero__eyebrow">{homeDesign === "vegas" ? "КАРТОЧНАЯ АРЕНА" : "ТВОЙ КАРТОЧНЫЙ КЛУБ"}</p>
        <h1 className="arena-hero__title">{homeDesign === "vegas" ? "VEGAS" : "МАРУСЬКА"} <span>АРЕНА</span></h1>
        <p className="arena-hero__subtitle">{homeDesign === "vegas" ? "ИГРАЙ. БЛЕФУЙ. ПОБЕЖДАЙ." : "Собирай друзей. Играй красиво. Побеждай."}</p>
      </section>
      )}

      <button type="button" className="quick-play" onClick={quickGame} disabled={finding} aria-busy={finding}>
        <span className="quick-play__icon">{finding ? <span className="ui-spinner" /> : <Icon name="play" size={30} />}</span>
        <span className="quick-play__title">Быстрая игра</span>
        <span className="quick-play__hint">Подберём стол по вашей ставке</span>
      </button>

      {me.daily.claimable > 0 && (
        <button type="button" className="news-card news-card--fresh daily-home" onClick={() => push('daily')}>
          <span className="news-card__icon" aria-hidden="true">🎁</span>
          <span className="news-card__body">
            <small>
              Задания и награды дня
              <b className="news-card__badge">{me.daily.claimable}</b>
            </small>
            <strong>Вас ждут награды — заберите их</strong>
          </span>
          <span className="news-card__arrow" aria-hidden="true">›</span>
        </button>
      )}

      <button type="button" className={`news-card${unseenNews ? ' news-card--fresh' : ''}`} onClick={() => push('news')}>
        <span className="news-card__icon" aria-hidden="true">📰</span>
        <span className="news-card__body">
          <small>
            Новости · {newsDate(latest.date)}
            {unseenNews > 0 && <b className="news-card__badge">новое</b>}
          </small>
          <strong>{latest.headline}</strong>
        </span>
        <span className="news-card__arrow" aria-hidden="true">›</span>
      </button>

      <InstallCard />

      {(homeDesign === 'daylight' || homeDesign === 'vegas') && (
        <>
      <button type="button" className="friends-play" onClick={() => push('friends')}>
        <span className="friends-play__icon"><Icon name="users" size={22} /></span>
        <span><strong>Играть с друзьями</strong><small>Пригласи знакомых за свой стол</small></span>
        <span className="friends-play__arrow" aria-hidden="true">›</span>
      </button>

      <div className="home-section-label"><span>ТВОЯ АРЕНА</span><i /></div>
        </>
      )}
      <div className="tile-grid">
        {(me.owner ? [...TILES, { icon: 'crown', title: 'Управление', page: 'owner' } as Tile] : TILES).map((tile) => {
          const count = counter(tile);
          return (
            <button key={tile.title} type="button" className="grid-tile" onClick={() => tile.page && push(tile.page)}>
              <span className="grid-tile__icon">
                <Icon name={tile.icon} size={36} />
                {count !== null && <span className={`grid-tile__count${typeof count === 'number' ? ' grid-tile__count--alert' : ''}`}>{count}</span>}
              </span>
              <span className="grid-tile__title">{tile.title}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Ivory bar: who I am on the left, what I have on the right. */
export function HomeBar() {
  const me = useMe();
  const { refreshMe } = useSession();
  const { push } = useNav();
  const toast = useToast();
  const [claiming, setClaiming] = useState(false);

  const topUpCredits = () => {
    if (!me.dailyCredits.available) {
      const at = me.dailyCredits.availableAt ? new Date(me.dailyCredits.availableAt) : null;
      toast(
        at
          ? `Бесплатные кредиты снова будут ${at.toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}`
          : `Бесплатные ${DAILY_CREDITS.amount} кредитов дают, когда на счёте меньше ${DAILY_CREDITS.belowBalance}`,
      );
      return;
    }
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
    <header className="home-bar">
      <button type="button" className="home-bar__me" onClick={() => push('profile')} aria-label="Мой профиль">
        <Avatar
          id={me.id}
          name={me.name}
          photoUrl={me.photoUrl}
          size={60}
          ring={me.equipped.frame ? ringOf(me.equipped.frame) : undefined}
          crown={Boolean(me.equipped.crown)}
        />
        <span className="home-bar__who">
          <strong>{me.name}</strong>
          <RatingBadge rating={me.stats.rating} streak={me.bonus.streak} />
        </span>
      </button>
      <div className="home-bar__wallet">
        <span className="home-bar__money">
          <Balance kind="credits" value={me.wallet.credits} />
          <button type="button" className={`plus${me.dailyCredits.available ? ' plus--glow' : ''}`} aria-label="Получить кредиты" onClick={topUpCredits} disabled={claiming}>
            <Icon name="plus" size={16} />
          </button>
        </span>
        <span className="home-bar__money">
          <Balance kind="coins" value={me.wallet.coins} compact />
          <Balance kind="diamonds" value={me.wallet.diamonds} compact />
          <button type="button" className="plus" aria-label="Магазин предметов" onClick={() => push('items')}>
            <Icon name="plus" size={16} />
          </button>
        </span>
      </div>
    </header>
  );
}
