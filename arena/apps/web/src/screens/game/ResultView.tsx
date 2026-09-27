import type { GameResultDto, PlayerInfo } from '@arena/shared';
import { Avatar, Balance, Button } from '@arena/ui';
import { useEffect } from 'react';
import { haptic } from '../../lib/telegram.js';
import { play } from '../../lib/sound.js';
import { useMe } from '../../session.js';

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

export function ResultView({ result, players, onClose }: { result: GameResultDto; players: PlayerInfo[]; onClose: () => void }) {
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
      {outcome === 'win' && (
        <div className="confetti" aria-hidden="true">
          {CONFETTI.map((c, i) => (
            <span key={i} style={{ left: `${c.x}%`, background: c.color, animationDelay: `${c.delay}ms`, animationDuration: `${c.duration}ms` }} />
          ))}
        </div>
      )}
      <div className="result__card">
        <span className="result__title">{outcome === 'win' ? 'Победа!' : outcome === 'lose' ? 'Вы дурак' : 'Ничья'}</span>
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
              </div>
            );
          })}
        </div>
        <Button size="lg" block variant="gold" onClick={onClose}>
          В лобби
        </Button>
      </div>
    </div>
  );
}
