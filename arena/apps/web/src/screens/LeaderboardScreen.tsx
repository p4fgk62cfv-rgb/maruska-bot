import type { LeaderboardBy, LeaderboardRowDto, SeasonDto } from '@arena/shared';
import { Avatar, Balance, EmptyState, Panel, RatingBadge, Tabs } from '@arena/ui';
import { useState } from 'react';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { QueryView, ScreenHeader } from './common.js';

type View = LeaderboardBy | 'season';

function Value({ row, by }: { row: LeaderboardRowDto; by: LeaderboardBy }) {
  if (by === 'winnings') return <Balance kind="credits" value={row.totalWinnings} compact />;
  if (by === 'wins') return <span className="board-row__value">{row.gamesWon}</span>;
  return null;
}

export default function LeaderboardScreen() {
  const [view, setView] = useState<View>('rating');
  const { openPlayer } = useNav();
  const board = useQuery<LeaderboardRowDto[]>(view === 'season' ? null : `/leaderboard?by=${view}`);
  const season = useQuery<SeasonDto | null>(view === 'season' ? '/season' : null);

  return (
    <div className="app-stack">
      <ScreenHeader title="Доска почёта" />
      <Tabs
        value={view}
        onChange={setView}
        items={[
          { value: 'rating', label: 'Рейтинг' },
          { value: 'winnings', label: 'Выигрыш' },
          { value: 'wins', label: 'Победы' },
          { value: 'season', label: 'Сезон' },
        ]}
      />
      {view === 'season' ? (
        <QueryView query={season}>
          {(s) =>
            !s ? (
              <EmptyState icon="clock" title="Сезон не идёт" text="В начале сезона все стартуют с нуля, а лучших награждают в конце." />
            ) : (
              <div className="app-list">
                <Panel>
                  <strong>{s.title}</strong>
                  <p className="app-muted">
                    до {new Date(s.endsAt).toLocaleDateString('ru-RU')} · вы: {s.me.place ? `${s.me.place} место` : 'ещё не играли'}, {s.me.seasonRating}
                  </p>
                </Panel>
                {s.top.map((row) => (
                  <Panel key={row.id} padded={false} className="board-row" role="button" tabIndex={0} onClick={() => openPlayer(row.id)}>
                    <span className={`board-row__place${row.place <= 3 ? ' board-row__place--top' : ''}`}>{row.place}</span>
                    <Avatar id={row.id} name={row.name} photoUrl={row.photoUrl} size={38} />
                    <div className="board-row__body">
                      <strong>{row.name}</strong>
                    </div>
                    <span className="board-row__value">{row.seasonRating}</span>
                  </Panel>
                ))}
              </div>
            )
          }
        </QueryView>
      ) : (
        <QueryView query={board}>
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState icon="medal" title="Пока пусто" text="Сыграйте первую партию — и попадёте на доску." />
            ) : (
              <div className="app-list">
                {rows.map((row) => (
                  <Panel key={row.id} padded={false} className="board-row" role="button" tabIndex={0} onClick={() => openPlayer(row.id)}>
                    <span className={`board-row__place${row.place <= 3 ? ' board-row__place--top' : ''}`}>{row.place}</span>
                    <Avatar id={row.id} name={row.name} photoUrl={row.photoUrl} size={38} />
                    <div className="board-row__body">
                      <strong>{row.name}</strong>
                      <RatingBadge rating={row.rating} />
                    </div>
                    <Value row={row} by={view as LeaderboardBy} />
                  </Panel>
                ))}
              </div>
            )
          }
        </QueryView>
      )}
    </div>
  );
}
