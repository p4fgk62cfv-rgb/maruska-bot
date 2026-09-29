import type { GameResultDto, PlayerInfo } from '@arena/shared';
import { Avatar, Balance, Button } from '@arena/ui';
import { useState } from 'react';
import { api } from '../../lib/api.js';
import { useEffect } from 'react';
import { haptic } from '../../lib/telegram.js';
import { play } from '../../lib/sound.js';
import { useMe } from '../../session.js';
import { useSettings } from '../../lib/settings.js';
import { useCountdown } from '../../lib/hooks.js';

const REASON: Record<string, string> = {
  cards: 'остался с картами',
  surrender: 'сдался',
  timeout: 'не успел сходить',
  last_attack: 'подкинул последнюю карту',
};
const REASON_ME: Record<string, string> = {
  cards: 'Вы остались с картами',
  surrender: 'Вы сдались',
  timeout: 'Вы не успели сходить',
  last_attack: 'Вы подкинули последнюю карту',
};

const COLORS = ['#f5c451', '#a78bfa', '#22d3ee', '#fb7185', '#34d399'];
const CONFETTI = Array.from({ length: 36 }, (_, i) => ({
  x: (i * 37) % 100,
  color: COLORS[i % COLORS.length]!,
  delay: (i * 53) % 700,
  duration: 1600 + ((i * 97) % 900),
}));

function AddFriend({ userId }: { userId: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle');
  if (state === 'done') return <span className="result__added">✓</span>;
  return (
    <button
      type="button"
      className="result__add"
      aria-label="Добавить в друзья"
      disabled={state === 'busy'}
      onClick={() => {
        setState('busy');
        api('/friends/requests', { method: 'POST', body: { userId } }).then(
          () => setState('done'),
          () => setState('idle'),
        );
      }}
    >
      +
    </button>
  );
}

/**
 * `onAgain`: the table stays together — back to the same chairs, everyone presses «Готов» for the next deal.
 * `onClose`: leave the table for the lobby.
 */
export function ResultView({
  result,
  players,
  onClose,
  onAgain,
  againDeadline = null,
  now,
}: {
  result: GameResultDto;
  players: PlayerInfo[];
  onClose: () => void;
  onAgain?: (() => void) | null;
  /** When the table stops holding the chairs for the next deal. */
  againDeadline?: number | null;
  now?: () => number;
}) {
  const left = useCountdown(againDeadline, now);
  const rewards = useSettings().rewardAnimations;
  const me = useMe();
  const mine = result.payouts.find((p) => p.userId === me.id);
  const outcome = result.kind === 'draw' ? 'draw' : result.loserId === me.id ? 'lose' : 'win';
  const loser = players.find((p) => p.userId === result.loserId);

  useEffect(() => {
    if (outcome === 'win') {
      haptic.success();
      play('win');
    } else if (outcome === 'lose') {
      haptic.error();
      play('lose');
    }
  }, [outcome]);

  return (
    <div className={`result result--${outcome}`} role="dialog" aria-modal="true">
      {outcome === 'win' && me.equipped.effect === 'effect_sparks' && (
        <div className="sparks" aria-hidden="true">
          {Array.from({ length: 18 }, (_, i) => (
            <span key={i} style={{ rotate: `${i * 20}deg`, animationDelay: `${(i % 3) * 120}ms` }} />
          ))}
        </div>
      )}
      {outcome === 'win' && rewards && (
        <div className="confetti" aria-hidden="true">
          {CONFETTI.map((c, i) => (
            <span key={i} style={{ left: `${c.x}%`, background: c.color, animationDelay: `${c.delay}ms`, animationDuration: `${c.duration}ms` }} />
          ))}
        </div>
      )}
      <div className="result__card">
        <span className="result__title">{result.reason === 'cancelled' ? 'Партия отменена' : outcome === 'win' ? 'Победа!' : outcome === 'lose' ? 'Вы дурак' : 'Ничья'}</span>
        {result.reason === 'cancelled' && <p className="app-muted">Модератор остановил партию. Ставки вернулись всем игрокам.</p>}
        {loser && result.kind === 'loser' && (
          <p className="app-muted">
            {loser.userId === me.id ? REASON_ME[result.reason ?? 'cards'] : `${loser.name} — ${REASON[result.reason ?? 'cards']}`}
          </p>
        )}
        {mine && (
          <div className="result__mine">
            <span className={mine.net >= 0 ? 'tx-plus' : 'tx-minus'}>
              {mine.net >= 0 ? '+' : '−'}
              <Balance kind="credits" value={Math.abs(mine.net)} />
            </span>
            {mine.ratingGain > 0 && (
              <span className="result__rating">
                +{mine.ratingGain} рейтинга{mine.bonusMultiplier > 1 ? ` · бонус ×${mine.bonusMultiplier}` : ''}
              </span>
            )}
          </div>
        )}
        <div className="result__list">
          {result.payouts.map((p) => {
            const info = players.find((x) => x.userId === p.userId);
            return (
              <div key={p.userId} className="result__row">
                <Avatar id={p.userId} name={info?.name ?? '?'} photoUrl={info?.photoUrl} size={30} />
                <span>{p.userId === me.id ? 'Вы' : info?.name}</span>
                <span className={p.net >= 0 ? 'tx-plus' : 'tx-minus'}>{p.net >= 0 ? `+${p.net}` : `−${Math.abs(p.net)}`}</span>
                {p.userId !== me.id ? <AddFriend userId={p.userId} /> : <span />}
              </div>
            );
          })}
        </div>
        {onAgain ? (
          <div className="result__actions">
            <Button size="lg" block variant="gold" onClick={onAgain}>
              Играть ещё
            </Button>
            {left !== null && left > 0 && (
              <p className="result__wait">
                Стол ждёт {Math.floor(left / 60000)}:{String(Math.floor((left % 60000) / 1000)).padStart(2, '0')} — потом свободные места займут другие
              </p>
            )}
            <Button block variant="ghost" onClick={onClose}>
              Выйти в лобби
            </Button>
          </div>
        ) : (
          <Button size="lg" block variant="gold" onClick={onClose}>
            В лобби
          </Button>
        )}
      </div>
    </div>
  );
}
