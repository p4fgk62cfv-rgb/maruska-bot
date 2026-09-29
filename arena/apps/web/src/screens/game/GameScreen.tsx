import { beats, rankOf, type CardId } from '@arena/game-engine';
import { FEATURE_PRICES, type RoomDto } from '@arena/shared';
import { Balance, BottomSheet, Button, PlayingCard } from '@arena/ui';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useCountdown } from '../../lib/hooks.js';
import { haptic } from '../../lib/telegram.js';
import { play, unlockAudio } from '../../lib/sound.js';
import { motionAllowed, settings, useSettings } from '../../lib/settings.js';
import { fly, MotionDirector } from './motion.js';
import { backOf } from '../../lib/cosmetics.js';
import { useRealtime, type LiveGame } from '../../realtime.js';
import { useMe, useSession } from '../../session.js';
import { useToast } from '../../toast.js';
import { sameRank, sortHand } from './cards.js';
import { Hand } from './Hand.js';
import { ResultView } from './ResultView.js';
import { PlayerSheet } from './PlayerSheet.js';
import { Payout } from './Payout.js';
import { api } from '../../lib/api.js';
import { DockAction, DockExtra, SeatTile, TableDock, TableTop } from './TableChrome.js';
import { EmojiSheet, useSeatEmojis } from './emoji.js';
import { Table, type PendingMove } from './Table.js';

type Sheet = null | 'menu' | 'emoji' | 'surrender' | 'discard' | { report: number };

export function GameScreen({ game }: { game: LiveGame }) {
  const me = useMe();
  const { socket, result, dismissGame, leaveRoom, onEvents, status, room } = useRealtime();
  const prefs = useSettings();
  const toast = useToast();
  const view = game.state;
  const a = view.actions;
  const [selected, setSelected] = useState<CardId[]>([]);
  const [sheet, setSheet] = useState<Sheet>(null);
  const sort = prefs.handSort;
  const rootRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);
  const director = useRef(new MotionDirector()).current;
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingMove | null>(null);
  const returning = useRef<Record<string, DOMRect>>({});
  const [drag, setDrag] = useState<{ card: CardId; hover: string | null } | null>(null);
  const emojis = useSeatEmojis(me.id);
  const [profileOf, setProfileOf] = useState<string | null>(null);
  const { refreshMe } = useSession();
  const [paid, setPaid] = useState<string | null>(null);
  const myNet = result?.payouts.find((p) => p.userId === me.id)?.net ?? 0;
  const payoutActive = Boolean(result) && myNet > 0 && paid !== view.gameId && prefs.rewardAnimations;
  // The stake left the wallet when the game started: show the balance as it is now.
  useEffect(() => {
    void refreshMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.gameId]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const gameId = view.gameId;

  const now = useCallback(() => socket.now(), [socket]);
  const left = useCountdown(view.turnDeadline, now);
  const progress = left !== null ? Math.min(1, left / view.rules.turnMs) : null;

  // My private labels about the people at this table.
  const opponentIds = view.players.filter((p) => p.id !== me.id).map((p) => p.id).join(',');
  useEffect(() => {
    if (!opponentIds) return;
    api<Record<string, string>>(`/players/notes?ids=${opponentIds}`).then(setNotes).catch(() => undefined);
  }, [opponentIds]);

  // A new state invalidates the selection unless those cards are still in hand.
  useEffect(() => {
    setSelected((s) => s.filter((c) => view.you?.hand.includes(c)));
  }, [view.version, view.you?.hand]);

  // Motion + sound: snapshot the table when events arrive, animate after the new state renders.
  useLayoutEffect(() => director.attach(rootRef.current, layerRef.current), [director]);
  useEffect(
    () =>
      onEvents((events) => {
        director.prepare(events, me.id);
        let sfx: Parameters<typeof play>[0] | null = null;
        for (const e of events) {
          if (e.type === 'CARD_PLAYED' || e.type === 'CARD_TRANSFERRED') sfx = 'card';
          else if (e.type === 'CARDS_TAKEN') sfx = 'take';
          else if (e.type === 'ROUND_FINISHED' && e.outcome === 'beaten') sfx = 'discard';
          else if (e.type === 'PLAYER_TURN' && e.playerId === me.id && !sfx) sfx = 'turn';
        }
        if (sfx) play(sfx);
      }),
    [onEvents, director, me.id],
  );
  useLayoutEffect(() => director.play(), [view.version, director]);
  // Opening deal, once, when the table is fresh.
  useLayoutEffect(() => {
    if (view.version <= 1 && view.table.length === 0 && view.discardCount === 0) {
      director.deal(me.id, view.players.map((p) => p.id), 6);
      play('deal');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [director]);

  // Last five seconds of my turn: a tick every second and a nudge.
  const secondsLeft = left !== null ? Math.ceil(left / 1000) : null;
  useEffect(() => {
    if (view.currentPlayer !== me.id || secondsLeft === null || secondsLeft > 5 || secondsLeft === 0) return;
    play('tick');
    if (secondsLeft === 5) haptic.warning();
  }, [secondsLeft, view.currentPlayer, me.id]);

  useEffect(() => {
    if (view.currentPlayer === me.id) haptic.tap();
  }, [view.currentPlayer, view.version, me.id]);

  const send = useCallback(
    async (msg: Parameters<typeof socket.send>[0]) => {
      setBusy(true);
      const reply = await socket.send(msg);
      setBusy(false);
      if (!reply.ok) {
        play('error');
        toast(reply.message, 'error');
      }
      else setSelected([]);
      return reply.ok;
    },
    [socket, toast],
  );

  // A pending move only counts until the server's next state arrives.
  const shown = pending && pending.version === view.version ? pending : null;
  const sorted = useMemo(() => sortHand(view.you?.hand ?? [], view.trump.suit, sort, prefs.sortDesc), [view.you?.hand, view.trump.suit, sort, prefs.sortDesc]);
  const hand = useMemo(() => (shown ? sorted.filter((c) => !shown.cards.includes(c)) : sorted), [sorted, shown]);

  // A refused move: the cards glide from the felt back into the hand.
  useLayoutEffect(() => {
    const back = returning.current;
    returning.current = {};
    for (const [card, from] of Object.entries(back)) {
      const el = rootRef.current?.querySelector<HTMLElement>(`.hand [data-card="${card}"]`);
      if (el && motionAllowed()) fly(el, from, el.getBoundingClientRect(), 0);
    }
  }, [pending]);
  const isDefender = view.defender === me.id && view.phase === 'defense';
  const undefended = view.table.map((p, i) => (p.defense ? -1 : i)).filter((i) => i >= 0);

  const playable = useMemo(() => {
    if (!game.features.hints) return null;
    return new Set<CardId>([...a.attack, ...(Object.keys(a.defend) as CardId[]), ...a.transfer]);
  }, [game.features.hints, a]);

  const hinted = drag?.card ?? (selected.length === 1 ? selected[0]! : null);
  const targets = hinted && game.features.hints ? (a.defend[hinted] ?? []) : [];

  const tapCard = (card: CardId) => {
    haptic.select();
    unlockAudio();
    setSelected((s) => {
      if (s.includes(card)) return s.filter((c) => c !== card);
      // Several cards only when leading with one rank.
      if (!isDefender && view.phase === 'attack' && sameRank([...s, card])) return [...s, card];
      return [card];
    });
  };

  /**
   * Optimistic move: the card lands on the felt at once instead of waiting a round trip for the
   * server. The server's state replaces it (same spot, so nothing jumps); a refusal sends it back.
   */
  const playNow = async (msg: Parameters<typeof send>[0], cards: CardId[], target: number | null): Promise<boolean> => {
    const from: Record<string, DOMRect> = {};
    for (const c of cards) {
      const el = rootRef.current?.querySelector<HTMLElement>(`.hand [data-card="${c}"]`);
      if (el) from[c] = el.getBoundingClientRect();
    }
    setPending({ cards, target, from, version: view.version });
    const ok = await send(msg);
    if (!ok) {
      // Remember where the cards were shown so they glide back into the hand.
      for (const c of cards) {
        const el = rootRef.current?.querySelector<HTMLElement>(`.felt [data-card="${c}"]`);
        if (el) returning.current[c] = el.getBoundingClientRect();
      }
      setPending(null);
    }
    return ok;
  };

  const leadable = (cards: CardId[]) => view.table.length === 0 || cards.every((c) => view.table.some((p) => rankOf(p.attack) === rankOf(c) || (p.defense && rankOf(p.defense as CardId) === rankOf(c))));

  const attack = (cards: CardId[]) => {
    const msg = cards.length === 1 ? ({ type: 'PLAY_CARD', gameId, card: cards[0]! } as const) : ({ type: 'PLAY_CARDS', gameId, cards } as const);
    return leadable(cards) ? playNow(msg, cards, null) : send(msg);
  };

  const defend = (card: CardId, target: number) => {
    const msg = { type: 'PLAY_CARD', gameId, card, target } as const;
    const pair = view.table[target];
    return pair && !pair.defense && beats(card, pair.attack, view.trump.suit) ? playNow(msg, [card], target) : send(msg);
  };

  const transfer = (card: CardId) => playNow({ type: 'TRANSFER', gameId, card }, [card], null);

  const doubleTap = (card: CardId) => {
    if (isDefender && undefended.length === 1) void defend(card, undefended[0]!);
    else if (a.canAttack) void attack([card]);
  };

  const tapPair = (index: number) => {
    const card = selected[0];
    if (card && isDefender && selected.length === 1 && undefended.includes(index)) void defend(card, index);
  };

  /** The drop zone under the finger; the dragged card itself (inside the hand) is ignored. */
  const dropAt = (x: number, y: number): string | null => {
    for (const el of document.elementsFromPoint(x, y)) {
      if (el.closest('.hand')) continue;
      const zone = el.closest<HTMLElement>('[data-drop]');
      if (zone) return zone.dataset.drop ?? null;
    }
    return null;
  };

  const dragMove = (card: CardId | null, x: number, y: number) => {
    if (!card) return setDrag(null);
    const hover = dropAt(x, y);
    setDrag((d) => (d && d.card === card && d.hover === hover ? d : { card, hover }));
  };

  /** Drag-and-drop move: onto the felt to lead or throw in, onto a card to beat it, onto «Перевести» to pass the attack. */
  const dropCard = async (card: CardId, x: number, y: number): Promise<boolean> => {
    unlockAudio();
    const zone = dropAt(x, y);
    if (!zone || busy) return false;
    const sameRankAsLead = view.table.length > 0 && rankOf(card) === rankOf(view.table[0]!.attack);

    if (zone === 'transfer') return a.canTransfer && sameRankAsLead ? transfer(card) : false;

    if (isDefender) {
      const index = zone.startsWith('pair:') ? Number(zone.slice(5)) : undefended.length === 1 ? undefended[0]! : -1;
      if (index >= 0 && undefended.includes(index)) return defend(card, index);
      if (a.canTransfer && sameRankAsLead) return transfer(card);
      if (undefended.length > 1) toast('Перетащите на карту, которую бьёте');
      return false;
    }

    if (!a.canAttack) return false;
    // Leading with several of one rank: the whole selection goes if the dragged card is part of it.
    const cards = selected.includes(card) && selected.length > 1 && sameRank(selected) ? selected : [card];
    return attack(cards);
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

  const labelOf = (p: { id: string; status: string; place: number | null }) => {
    if (view.cheaters.includes(p.id)) return { text: 'Шулер', tone: 'alert' as const };
    if (p.status === 'out') return { text: `${p.place} место`, tone: 'muted' as const };
    if (p.status === 'left') return { text: 'Сдался', tone: 'muted' as const };
    if (infoOf(p.id)?.connected === false) return { text: 'Нет связи', tone: 'alert' as const };
    const role = roleOf(p.id);
    return role === 'attacker' ? { text: 'Ходит', tone: 'attack' as const } : role === 'defender' ? { text: 'Отбивается', tone: 'defend' as const } : null;
  };
  const bubbleOf = (id: string) => {
    if (view.phase === 'taking' && id === view.defender) return { text: 'Беру', tone: 'take' as const };
    if (view.passed.includes(id)) return { text: undefended.length === 0 ? 'Бито' : 'Пас', tone: 'pass' as const };
    return null;
  };
  const seatOf = (id: string) => {
    const info = infoOf(id);
    return { id, name: info?.name ?? 'Игрок', photoUrl: info?.photoUrl ?? null, frame: info?.frame ?? null, crown: info?.crown ?? null };
  };
  const back = backOf(me.equipped.cardBack);
  const { rules } = view;
  const tableSettings: RoomDto['settings'] = room?.settings ?? {
    stake: 0,
    players: view.players.length,
    deckSize: rules.deckSize as RoomDto['settings']['deckSize'],
    speed: rules.speed,
    variant: rules.variant,
    throwIn: rules.throwIn,
    fairness: rules.fairness,
    ending: rules.ending,
  };
  const tileSize = opponents.length > 3 ? 50 : 58;

  const actions: { key: string; text: string; tone?: 'main' | 'alt' | 'gold'; run: () => void }[] = [];
  if (canTransferSelected) actions.push({ key: 'transfer', text: 'Перевести', tone: 'gold', run: () => void transfer(selected[0]!) });
  if (selected.length > 0 && a.canAttack && !isDefender) actions.push({ key: 'attack', text: selected.length > 1 ? `Хожу (${selected.length})` : 'Хожу', run: () => void attack(selected) });
  if (selected.length === 1 && isDefender && undefended.length === 1) actions.push({ key: 'defend', text: 'Бью', run: () => void defend(selected[0]!, undefended[0]!) });
  if (a.take) actions.push({ key: 'take', text: 'Беру', run: () => void send({ type: 'TAKE_CARDS', gameId }) });
  if (a.pass) actions.push({ key: 'pass', text: view.phase === 'defense' && undefended.length === 0 ? 'Бито' : 'Пас', tone: 'alt', run: () => void send({ type: 'PASS', gameId }) });

  return (
    <div className="game" ref={rootRef}>
      <div className="motion-layer" ref={layerRef} />
      {status !== 'open' && <div className="game__banner">Соединение восстанавливается…</div>}

      <TableTop settings={tableSettings} button={{ icon: 'menu', label: 'Меню', onClick: () => setSheet('menu') }} />

      <div className={`game__opponents game__opponents--${opponents.length}`}>
        {opponents.map((p, i) => (
          <div key={p.id} className="game__opp" style={{ ['--arc' as string]: `${arcOffset(i, opponents.length)}px` }}>
            <SeatTile
              seat={seatOf(p.id)}
              anchor
              size={tileSize}
              cards={p.status === 'active' ? p.cardCount : 0}
              back={back}
              active={view.currentPlayer === p.id}
              progress={view.currentPlayer === p.id ? progress : null}
              label={labelOf(p)}
              bubble={p.status === 'active' ? bubbleOf(p.id) : null}
              note={notes[p.id] ?? null}
              onOpen={() => setProfileOf(p.id)}
              emoji={emojis[p.id] ?? null}
              dim={p.status !== 'active'}
              offline={infoOf(p.id)?.connected === false}
            />
          </div>
        ))}
      </div>

      <Table
        view={view}
        cardWidth={Math.min(74, (Math.min(window.innerWidth, 560) - 70) / 3.7)}
        targets={targets}
        onPair={tapPair}
        back={back}
        onReport={view.rules.fairness === 'cheaters' && a.canReport ? (seq) => setSheet({ report: seq }) : null}
        hover={drag?.hover ?? null}
        dragging={drag !== null}
        pending={shown}
        transferSlot={
          a.canTransfer
            ? {
                active: canTransferSelected,
                onDrop: () => canTransferSelected && void transfer(selected[0]!),
              }
            : null
        }
      />
      {isDefender && selected.length === 1 && undefended.length > 1 && !drag && <p className="game__tip">Перетащите карту на ту, которую бьёте, или нажмите на неё</p>}

      <Hand
        cards={hand}
        trump={view.trump.suit}
        selected={selected}
        playable={playable}
        cardWidth={Math.min(96, Math.max(64, (Math.min(window.innerWidth, 560) - 16) / 4.3))}
        onTap={tapCard}
        onDoubleTap={prefs.doubleTap ? doubleTap : tapCard}
        onSwipeRight={() => settings.set({ handSort: sort === 'suit' ? 'rank' : 'suit' })}
        onDragMove={dragMove}
        onDrop={dropCard}
      />

      <TableDock
        actions={
          actions.length === 0 && myTurn ? (
            <span className="dock-yourturn" key={`turn-${view.version}`}>Ваш ход</span>
          ) : mine && mine.status !== 'active' && view.status === 'playing' ? (
            <span className="dock-watching">Смотрите, как доигрывают</span>
          ) : actions.slice(0, 2).map((act) => (
              <DockAction key={act.key} tone={act.tone} busy={busy} onClick={act.run}>
                {act.text}
              </DockAction>
            ))
        }
        me={
          <button type="button" className="table-dock__avatar" onClick={() => setSheet('emoji')} aria-label="Отправить смайлик">
            {mine && (
              <SeatTile
                seat={seatOf(me.id)}
                size={56}
                active={myTurn}
                progress={myTurn ? progress : null}
                label={mine.status === 'active' ? null : labelOf(mine)}
                bubble={mine.status === 'active' ? bubbleOf(mine.id) : null}
                emoji={emojis[me.id] ?? null}
              />
            )}
          </button>
        }
        extras={
          <>
            <span className="dock-extras">
            <DockExtra icon="undo" label="Вернуть карту" price={FEATURE_PRICES.undo} disabled={!game.features.canUndo || busy} onClick={() => void send({ type: 'UNDO_MOVE', gameId })} />
            <DockExtra icon="eye" label="Подсветка карт" price={game.features.hints ? null : FEATURE_PRICES.hints} on={game.features.hints} disabled={game.features.hints || busy} onClick={() => void buy('hints')} />
            <DockExtra
              icon="cards"
              label={game.features.discardReminder ? 'Показать отбой' : 'Напомнить отбой'}
              price={game.features.discardReminder ? null : FEATURE_PRICES.discardReminder}
              on={game.features.discardReminder}
              disabled={busy}
              onClick={() => (game.features.discardReminder ? setSheet('discard') : void buy('discardReminder'))}
            />
            </span>
            <span className={`dock-balance${paid === gameId ? ' dock-balance--bump' : ''}`} data-balance key={paid === gameId ? 'after' : 'before'}>
              <Balance kind="credits" value={me.wallet.credits} compact />
            </span>
          </>
        }
      />

      <BottomSheet open={sheet === 'menu'} title="Меню" onClose={() => setSheet(null)}>
        <div className="app-list">
          <Button block variant="ghost" icon="heart" onClick={() => setSheet('emoji')}>Смайлик</Button>
          <p className="app-muted">
            Перетащите карту пальцем: на стол — сходить или подкинуть, на карту соперника — побить её, на «Перевести» — перевести. Двойной тап по карте — сразу сыграть. Свайп вправо по руке — сменить сортировку. Внизу справа — подсказки за монеты: вернуть карту ({FEATURE_PRICES.undo}), подсветка ({FEATURE_PRICES.hints}), отбой ({FEATURE_PRICES.discardReminder}).
          </p>
          {mine?.status === 'active' && (
            <Button block variant="danger" icon="flag" onClick={() => setSheet('surrender')}>Сдаться</Button>
          )}
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === 'surrender'} title="Сдаться?" onClose={() => setSheet(null)}>
        <div className="app-stack">
          <p className="app-muted">Вы проиграете партию и потеряете ставку.</p>
          <Button block variant="danger" onClick={() => (setSheet(null), void send({ type: 'LEAVE_GAME', gameId }))}>Сдаться</Button>
        </div>
      </BottomSheet>

      <EmojiSheet open={sheet === 'emoji'} pack={me.equipped.emoji} onClose={() => setSheet(null)} onPick={(emoji) => void send({ type: 'SEND_EMOJI', gameId, emoji })} />

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

      <PlayerSheet
        userId={profileOf}
        gameId={gameId}
        onClose={() => setProfileOf(null)}
        onNote={(id, note) => setNotes((n) => {
          const next = { ...n };
          if (note) next[id] = note;
          else delete next[id];
          return next;
        })}
      />

      {payoutActive && <Payout amount={myNet} target="[data-balance]" onDone={() => { setPaid(gameId); void refreshMe(); }} />}
      {result && !payoutActive && (
        <ResultView
          result={result}
          players={game.players}
          onAgain={room && !room.tournament ? dismissGame : null}
          onClose={() => {
            // Leaving the table frees the chair for someone else; the result closes either way.
            if (room && !room.tournament) void leaveRoom().catch(() => undefined).finally(dismissGame);
            else dismissGame();
          }}
        />
      )}
    </div>
  );
}

/** Opponents in play order, starting with the player after me. */
/** Opponents sit on an arc: the outer seats a little lower, like around a real table. */
function arcOffset(index: number, count: number): number {
  if (count < 3) return 0;
  const center = (count - 1) / 2;
  const d = Math.abs(index - center) / center;
  return Math.round(d * d * 30);
}

function rotate<T extends { id: string; seat: number }>(players: T[], myId: string): T[] {
  const mySeat = players.find((p) => p.id === myId)?.seat ?? 0;
  return [...players].filter((p) => p.id !== myId).sort((a, b) => ((a.seat - mySeat + 10) % 10) - ((b.seat - mySeat + 10) % 10));
}
