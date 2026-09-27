import { rankOf, type CardId } from '@arena/game-engine';
import { EMOJIS, FEATURE_PRICES } from '@arena/shared';
import { BottomSheet, Button, IconButton, PlayingCard } from '@arena/ui';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { safeStorage, useCountdown } from '../../lib/hooks.js';
import { haptic } from '../../lib/telegram.js';
import { useRealtime, type LiveGame } from '../../realtime.js';
import { useMe } from '../../session.js';
import { useToast } from '../../toast.js';
import { sameRank, sortHand } from './cards.js';
import { Hand } from './Hand.js';
import { ResultView } from './ResultView.js';
import { Seat } from './Seat.js';
import { Table } from './Table.js';

type Sheet = null | 'menu' | 'emoji' | 'surrender' | 'discard' | { report: number };
const SORT_KEY = 'arena.handSort';

export function GameScreen({ game }: { game: LiveGame }) {
  const me = useMe();
  const { socket, result, dismissGame, onEmoji, status } = useRealtime();
  const toast = useToast();
  const view = game.state;
  const a = view.actions;
  const [selected, setSelected] = useState<CardId[]>([]);
  const [sheet, setSheet] = useState<Sheet>(null);
  const [sort, setSort] = useState<'suit' | 'rank'>(() => safeStorage.get(SORT_KEY, 'suit'));
  const [busy, setBusy] = useState(false);
  const [emojis, setEmojis] = useState<Record<string, string>>({});
  const gameId = view.gameId;

  const now = useCallback(() => socket.now(), [socket]);
  const left = useCountdown(view.turnDeadline, now);
  const progress = left !== null ? Math.min(1, left / view.rules.turnMs) : null;

  // A new state invalidates the selection unless those cards are still in hand.
  useEffect(() => {
    setSelected((s) => s.filter((c) => view.you?.hand.includes(c)));
  }, [view.version, view.you?.hand]);

  useEffect(
    () =>
      onEmoji((userId, emoji) => {
        setEmojis((e) => ({ ...e, [userId]: emoji }));
        window.setTimeout(() => setEmojis((e) => (e[userId] === emoji ? { ...e, [userId]: '' } : e)), 2500);
      }),
    [onEmoji],
  );

  useEffect(() => {
    if (view.currentPlayer === me.id) haptic.tap();
  }, [view.currentPlayer, view.version, me.id]);

  const send = useCallback(
    async (msg: Parameters<typeof socket.send>[0]) => {
      setBusy(true);
      const reply = await socket.send(msg);
      setBusy(false);
      if (!reply.ok) toast(reply.message, 'error');
      else setSelected([]);
      return reply.ok;
    },
    [socket, toast],
  );

  const hand = useMemo(() => sortHand(view.you?.hand ?? [], view.trump.suit, sort), [view.you?.hand, view.trump.suit, sort]);
  const isDefender = view.defender === me.id && view.phase === 'defense';
  const undefended = view.table.map((p, i) => (p.defense ? -1 : i)).filter((i) => i >= 0);

  const playable = useMemo(() => {
    if (!game.features.hints) return null;
    return new Set<CardId>([...a.attack, ...(Object.keys(a.defend) as CardId[]), ...a.transfer]);
  }, [game.features.hints, a]);

  const targets = selected.length === 1 && game.features.hints ? (a.defend[selected[0]!] ?? []) : [];

  const tapCard = (card: CardId) => {
    haptic.select();
    setSelected((s) => {
      if (s.includes(card)) return s.filter((c) => c !== card);
      // Several cards only when leading with one rank.
      if (!isDefender && view.phase === 'attack' && sameRank([...s, card])) return [...s, card];
      return [card];
    });
  };

  const attack = (cards: CardId[]) =>
    send(cards.length === 1 ? { type: 'PLAY_CARD', gameId, card: cards[0]! } : { type: 'PLAY_CARDS', gameId, cards });

  const defend = (card: CardId, target: number) => send({ type: 'PLAY_CARD', gameId, card, target });

  const doubleTap = (card: CardId) => {
    if (isDefender && undefended.length === 1) void defend(card, undefended[0]!);
    else if (a.canAttack) void attack([card]);
  };

  const tapPair = (index: number) => {
    const card = selected[0];
    if (card && isDefender && selected.length === 1 && undefended.includes(index)) void defend(card, index);
  };

  const canTransferSelected =
    a.canTransfer && selected.length === 1 && view.table.length > 0 && rankOf(selected[0]!) === rankOf(view.table[0]!.attack);

  const buy = async (feature: 'hints' | 'discardReminder') => {
    setSheet(null);
    await send({ type: 'USE_FEATURE', gameId, feature });
    if (feature === 'discardReminder') setSheet('discard');
  };

  const myTurn = view.currentPlayer === me.id;
  const opponents = rotate(view.players, me.id);
  const mine = view.players.find((p) => p.id === me.id);
  const infoOf = (id: string) => game.players.find((p) => p.userId === id);
  const roleOf = (id: string) => (id === view.attacker ? 'attacker' : id === view.defender ? 'defender' : null);

  return (
    <div className="game">
      {status !== 'open' && <div className="game__banner">Соединение восстанавливается…</div>}

      <div className={`game__opponents game__opponents--${opponents.length}`}>
        {opponents.map((p) => (
          <Seat
            key={p.id}
            player={p}
            info={infoOf(p.id)}
            role={roleOf(p.id)}
            active={view.currentPlayer === p.id}
            progress={view.currentPlayer === p.id ? progress : null}
            passed={view.passed.includes(p.id)}
            cheater={view.cheaters.includes(p.id)}
            emoji={emojis[p.id] || null}
            compact={opponents.length > 3}
          />
        ))}
      </div>

      <Table
        view={view}
        cardWidth={Math.min(62, (Math.min(window.innerWidth, 560) - 110) / 3.6)}
        targets={targets}
        onPair={tapPair}
        onReport={view.rules.fairness === 'cheaters' && a.canReport ? (seq) => setSheet({ report: seq }) : null}
      />

      <div className="game__me">
        <div className="game__me-row">
          <button type="button" className="game__me-avatar" onClick={() => setSheet('emoji')} aria-label="Отправить смайлик">
            {mine && (
              <Seat
                player={mine}
                info={infoOf(me.id)}
                role={roleOf(me.id)}
                active={myTurn}
                progress={myTurn ? progress : null}
                passed={view.passed.includes(me.id)}
                cheater={view.cheaters.includes(me.id)}
                emoji={emojis[me.id] || null}
                compact
              />
            )}
          </button>
          <div className="game__actions">
            {selected.length > 0 && a.canAttack && !isDefender && (
              <Button loading={busy} onClick={() => void attack(selected)}>
                Хожу{selected.length > 1 ? ` (${selected.length})` : ''}
              </Button>
            )}
            {selected.length === 1 && isDefender && undefended.length === 1 && (
              <Button loading={busy} onClick={() => void defend(selected[0]!, undefended[0]!)}>Бью</Button>
            )}
            {canTransferSelected && (
              <Button variant="gold" loading={busy} onClick={() => void send({ type: 'TRANSFER', gameId, card: selected[0]! })}>
                Перевести
              </Button>
            )}
            {a.take && <Button variant="danger" loading={busy} onClick={() => void send({ type: 'TAKE_CARDS', gameId })}>Беру</Button>}
            {a.pass && (
              <Button variant="ghost" loading={busy} onClick={() => void send({ type: 'PASS', gameId })}>
                {view.phase === 'defense' && undefended.length === 0 ? 'Бито' : 'Пас'}
              </Button>
            )}
          </div>
          <IconButton icon="more" label="Меню" onClick={() => setSheet('menu')} />
        </div>

        {myTurn && left !== null && (
          <div className="game__turnbar" aria-hidden="true">
            <span style={{ transform: `scaleX(${progress ?? 0})` }} className={(progress ?? 1) < 0.25 ? 'game__turnbar--low' : ''} />
          </div>
        )}
        {isDefender && selected.length === 1 && undefended.length > 1 && <p className="game__tip">Нажмите на карту на столе, которую хотите побить</p>}

        <Hand
          cards={hand}
          trump={view.trump.suit}
          selected={selected}
          playable={playable}
          cardWidth={Math.min(74, Math.max(56, window.innerWidth / 5.6))}
          onTap={tapCard}
          onDoubleTap={doubleTap}
          onSwipeRight={() => {
            const next = sort === 'suit' ? 'rank' : 'suit';
            setSort(next);
            safeStorage.set(SORT_KEY, next);
          }}
        />
      </div>

      <BottomSheet open={sheet === 'menu'} title="Меню" onClose={() => setSheet(null)}>
        <div className="app-list">
          {game.features.canUndo && (
            <Button block variant="ghost" onClick={() => (setSheet(null), void send({ type: 'UNDO_MOVE', gameId }))}>
              Вернуть карту · {FEATURE_PRICES.undo} монета
            </Button>
          )}
          <Button block variant="ghost" disabled={game.features.hints} onClick={() => void buy('hints')}>
            {game.features.hints ? 'Подсветка включена' : `Подсветка карт · ${FEATURE_PRICES.hints} монеты`}
          </Button>
          <Button block variant="ghost" onClick={() => (game.features.discardReminder ? setSheet('discard') : void buy('discardReminder'))}>
            {game.features.discardReminder ? 'Показать отбой' : `Напомнить отбой · ${FEATURE_PRICES.discardReminder} монеты`}
          </Button>
          <p className="app-muted">Двойной тап по карте — сразу сыграть. Свайп вправо по руке — сменить сортировку.</p>
          {mine?.status === 'active' && (
            <Button block variant="danger" onClick={() => setSheet('surrender')}>Сдаться</Button>
          )}
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === 'surrender'} title="Сдаться?" onClose={() => setSheet(null)}>
        <div className="app-stack">
          <p className="app-muted">Вы проиграете партию и потеряете ставку.</p>
          <Button block variant="danger" onClick={() => (setSheet(null), void send({ type: 'LEAVE_GAME', gameId }))}>Сдаться</Button>
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === 'emoji'} title="Смайлик" onClose={() => setSheet(null)}>
        <div className="emoji-grid">
          {EMOJIS.map((e) => (
            <button key={e} type="button" onClick={() => (setSheet(null), void send({ type: 'SEND_EMOJI', gameId, emoji: e }))}>
              {e}
            </button>
          ))}
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === 'discard'} title={`Отбой · ${view.discardCount}`} onClose={() => setSheet(null)}>
        <div className="discard-grid">
          {(view.discard ?? []).map((c) => (
            <PlayingCard key={c} card={c} width={40} />
          ))}
        </div>
      </BottomSheet>

      <BottomSheet open={typeof sheet === 'object' && sheet !== null} title="Шулер?" onClose={() => setSheet(null)}>
        <div className="app-stack">
          <p className="app-muted">Если карта сыграна не по правилам, она и все карты после неё вернутся владельцам.</p>
          <Button
            block
            variant="gold"
            onClick={() => {
              if (typeof sheet === 'object' && sheet) void send({ type: 'REPORT_CHEAT', gameId, seq: sheet.report });
              setSheet(null);
            }}
          >
            Поймать шулера
          </Button>
        </div>
      </BottomSheet>

      {result && <ResultView result={result} players={game.players} onClose={dismissGame} />}
    </div>
  );
}

/** Opponents in play order, starting with the player after me. */
function rotate<T extends { id: string; seat: number }>(players: T[], myId: string): T[] {
  const mySeat = players.find((p) => p.id === myId)?.seat ?? 0;
  return [...players].filter((p) => p.id !== myId).sort((a, b) => ((a.seat - mySeat + 10) % 10) - ((b.seat - mySeat + 10) % 10));
}
