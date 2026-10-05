import type { TrainingSeatDto, TrainingTableDto } from '@arena/shared';
import { PlayingCard } from '@arena/ui';
import { useEffect, useState } from 'react';
import { useRealtime } from '../realtime.js';
import { ScreenFallback, ScreenHeader } from './common.js';

/** «Тренировочный зал»: the three tables where the bots train, live and with open cards. */
export default function TrainingScreen() {
  const { socket } = useRealtime();
  const [tables, setTables] = useState<TrainingTableDto[] | null>(null);

  useEffect(() => {
    const offMsg = socket.onMessage((m) => {
      if (m.type === 'TRAINING_TABLES') setTables(m.tables);
      else if (m.type === 'TRAINING_TABLE') {
        setTables((list) => {
          const rest = (list ?? []).filter((t) => t.key !== m.table.key);
          return [...rest, m.table].sort((a, b) => order(a.key) - order(b.key));
        });
      }
    });
    const offOpen = socket.onOpen(() => void socket.send({ type: 'TRAINING_SUBSCRIBE' }));
    return () => {
      offMsg();
      offOpen();
      void socket.send({ type: 'TRAINING_UNSUBSCRIBE' });
    };
  }, [socket]);

  return (
    <div className="app-stack training-hall">
      <ScreenHeader title="Тренировочный зал" subtitle="Боты учатся играть — карты открыты" />
      <p className="training-hall__intro">
        За каждым столом <b>Чемпион</b> — лучшая на сейчас версия бота — играет с <b>Претендентом</b>, изменённой копией, которую
        обучение проверяет прямо сейчас. Здесь партии идут в обычном темпе, а в фоне те же боты успевают сыграть тысячи партий в минуту.
      </p>
      {tables === null ? (
        <ScreenFallback />
      ) : tables.length === 0 ? (
        <p className="app-muted">Столы откроются через минуту после запуска сервера.</p>
      ) : (
        tables.map((t, i) => <TrainingTable key={t.key} n={i + 1} table={t} />)
      )}
    </div>
  );
}

const order = (key: string) => ['podkidnoy', 'perevodnoy', 'cheaters'].indexOf(key);

function TrainingTable({ n, table }: { n: number; table: TrainingTableDto }) {
  return (
    <section className="tt">
      <header className="tt__head">
        <span className="tt__n">{n}</span>
        <span className="tt__title">
          <strong>{table.title}</strong>
          <small>
            Партия №{table.game} · Чемпион {table.score.champion} : {table.score.challenger} Претендент
          </small>
        </span>
      </header>
      <div className="tt__felt">
        {table.seats.map((seat) => (
          <Seat key={seat.id} seat={seat} />
        ))}
        <div className="tt__middle">
          <div className="tt__stock">
            {table.trump.inStock ? <PlayingCard card={table.trump.card} width={30} /> : <span className="tt__trump-suit">козырь</span>}
            <small>колода {table.deck}</small>
            <small>отбой {table.discard}</small>
          </div>
          <div className="tt__pairs">
            {table.table.length === 0 ? (
              <span className="tt__empty">стол пуст</span>
            ) : (
              table.table.map((p, i) => (
                <span key={i} className="tt__pair">
                  <PlayingCard card={p.attack} width={30} />
                  {p.defense && (
                    <span className="tt__cover">
                      <PlayingCard card={p.defense} width={30} />
                    </span>
                  )}
                </span>
              ))
            )}
          </div>
        </div>
        <p className={`tt__last${table.result ? ' tt__last--result' : ''}`}>{table.result ?? table.last ?? ''}</p>
      </div>
    </section>
  );
}

function Seat({ seat }: { seat: TrainingSeatDto }) {
  return (
    <div className={`tt-seat tt-seat--${seat.role}${seat.status !== 'active' ? ' tt-seat--out' : ''}`}>
      <span className="tt-seat__name">
        {seat.attacker && <span title="Ходит">⚔️</span>}
        {seat.defender && <span title="Отбивается">🛡️</span>}
        {seat.name}
        <small>{seat.status === 'active' ? `${seat.hand.length} карт` : 'вышел'}</small>
      </span>
      <span className="tt-seat__hand">
        {seat.hand.map((c) => (
          <PlayingCard key={c} card={c} width={26} />
        ))}
      </span>
    </div>
  );
}
