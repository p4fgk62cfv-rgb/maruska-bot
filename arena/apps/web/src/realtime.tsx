import type { GameEvent, PlayerView } from '@arena/game-engine';
import type { FriendRequestsDto, GameResultDto, MyRoomDto, PlayerInfo, Presence, PublicUserDto, RoomDto, ServerMessage } from '@arena/shared';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, getToken } from './lib/api.js';
import { GameSocket, type SocketStatus } from './lib/socket.js';
import { haptic } from './lib/telegram.js';
import { useSession } from './session.js';
import { useToast } from './toast.js';

export interface LiveGame {
  state: PlayerView;
  players: PlayerInfo[];
  features: { hints: boolean; discardReminder: boolean; canUndo: boolean };
  /** The table waits for a player who lost the connection on their turn. */
  waiting: { userId: string; until: number } | null;
}

export interface RoomInvite {
  from: PublicUserDto;
  room: RoomDto;
  invite: string;
}

interface RealtimeValue {
  socket: GameSocket;
  status: SocketStatus;
  room: RoomDto | null;
  invite: MyRoomDto['invite'] | null;
  game: LiveGame | null;
  result: GameResultDto | null;
  /** Called by screens after REST calls that put the player into a room. */
  enterRoom: (mine: MyRoomDto) => void;
  leaveRoom: () => Promise<void>;
  dismissGame: () => void;
  /** Incoming friend requests waiting for an answer — the badge on «Друзья». */
  requestCount: number;
  refreshRequests: () => void;
  invites: RoomInvite[];
  /** Live presence of friends and favourites, newer than any list fetched before. */
  presence: Record<string, Presence>;
  dismissInvite: (roomId: string) => void;
  /** Subscribe to animation events and emoji. */
  onEvents: (listener: (events: GameEvent[]) => void) => () => void;
  onEmoji: (listener: (userId: string, emoji: string) => void) => () => void;
}

const RealtimeContext = createContext<RealtimeValue | null>(null);

/** Owns the socket and the player's current room/game; every screen reads from here. */
export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { state: session, refreshMe, renew } = useSession();
  const toast = useToast();
  const socket = useMemo(() => new GameSocket(getToken, renew), [renew]);
  const [status, setStatus] = useState<SocketStatus>(socket.status);
  const [room, setRoom] = useState<RoomDto | null>(null);
  const [invite, setInvite] = useState<MyRoomDto['invite'] | null>(null);
  const [game, setGame] = useState<LiveGame | null>(null);
  const [result, setResult] = useState<GameResultDto | null>(null);
  const [requestCount, setRequestCount] = useState(0);
  const [invites, setInvites] = useState<RoomInvite[]>([]);
  const [presence, setPresence] = useState<Record<string, Presence>>({});
  const eventListeners = useRef(new Set<(e: GameEvent[]) => void>());
  const emojiListeners = useRef(new Set<(u: string, e: string) => void>());
  const myId = session.status === 'ready' ? session.me.id : null;

  useEffect(() => {
    if (session.status !== 'ready') return;
    socket.start();
    // Resume a room or game the player left by closing the app.
    api<MyRoomDto | null>('/me/active').then((mine) => {
      if (mine) {
        setRoom(mine.room);
        setInvite(mine.invite);
      }
    }).catch(() => undefined);
    return () => socket.stop();
  }, [session.status, socket]);

  const refreshRequests = useCallback(() => {
    api<FriendRequestsDto>('/friends/requests')
      .then((r) => setRequestCount(r.incoming.length))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if (session.status === 'ready') refreshRequests();
  }, [session.status, refreshRequests]);

  useEffect(() => socket.onStatus(setStatus), [socket]);

  useEffect(
    () =>
      socket.onMessage((msg: ServerMessage) => {
        switch (msg.type) {
          case 'ROOM_UPDATED':
          case 'ROOM_JOINED':
            if (!msg.room.seats.some((s) => s.userId === myId)) return;
            if (msg.room.status === 'closed' || msg.room.status === 'finished') {
              setRoom((current) => (current?.id === msg.room.id ? null : current));
            } else setRoom(msg.room);
            return;
          case 'ROOM_LEFT':
            if (msg.userId === myId) {
              setRoom(null);
              setInvite(null);
            } else setRoom(msg.room);
            return;
          case 'GAME_STARTED':
            haptic.success();
            setResult(null);
            return;
          case 'GAME_STATE':
            setGame({ state: msg.state, players: msg.players, features: msg.features, waiting: msg.waiting ?? null });
            return;
          case 'GAME_EVENTS':
            for (const l of eventListeners.current) l(msg.events);
            return;
          case 'EMOJI':
            for (const l of emojiListeners.current) l(msg.userId, msg.emoji);
            return;
          case 'GAME_FINISHED':
            setResult(msg.result);
            // A casual table stays together for the next deal; a tournament match room is gone.
            setRoom((current) => (current?.tournament ? null : current));
            void refreshMe();
            return;
          case 'FRIEND_REQUEST':
            haptic.tap();
            toast(`${msg.from.name} хочет добавить вас в друзья`, 'info');
            setRequestCount((n) => n + 1);
            return;
          case 'FRIEND_ACCEPTED':
            toast(`${msg.friend.name} теперь ваш друг`, 'success');
            return;
          case 'FRIEND_PRESENCE':
            setPresence((map) => ({ ...map, [msg.userId]: msg.presence }));
            return;
          case 'FRIEND_FREE':
            haptic.success();
            setPresence((map) => ({ ...map, [msg.friend.id]: msg.presence }));
            toast(`${msg.friend.name} закончил(а) партию — можно звать в игру`, 'success');
            return;
          case 'TOURNAMENT_MATCH':
            haptic.success();
            toast(`${msg.title}: ваш матч начинается — нажмите «Готов»`, 'success');
            return;
          case 'ROOM_INVITE':
            haptic.success();
            setInvites((list) => [...list.filter((i) => i.room.id !== msg.room.id), { from: msg.from, room: msg.room, invite: msg.invite }]);
            return;
          case 'ERROR':
            if (!msg.rid) toast(msg.message, 'error');
            return;
          default:
            return;
        }
      }),
    [socket, myId, refreshMe, toast],
  );

  const enterRoom = useCallback((mine: MyRoomDto) => {
    setRoom(mine.room);
    setInvite(mine.invite);
    setResult(null);
    setGame(null);
  }, []);

  const leaveRoom = useCallback(async () => {
    if (!room) return;
    await api(`/rooms/${room.id}/leave`, { method: 'POST' });
    setRoom(null);
    setInvite(null);
  }, [room]);

  const dismissGame = useCallback(() => {
    setGame(null);
    setResult(null);
  }, []);

  const dismissInvite = useCallback((roomId: string) => setInvites((list) => list.filter((i) => i.room.id !== roomId)), []);

  const onEvents = useCallback((l: (e: GameEvent[]) => void) => {
    eventListeners.current.add(l);
    return () => void eventListeners.current.delete(l);
  }, []);
  const onEmoji = useCallback((l: (u: string, e: string) => void) => {
    emojiListeners.current.add(l);
    return () => void emojiListeners.current.delete(l);
  }, []);

  const value = useMemo(
    () => ({
      socket, status, room, invite, game, result, enterRoom, leaveRoom, dismissGame, onEvents, onEmoji,
      requestCount, refreshRequests, invites, dismissInvite, presence,
    }),
    [socket, status, room, invite, game, result, enterRoom, leaveRoom, dismissGame, onEvents, onEmoji, requestCount, refreshRequests, invites, dismissInvite, presence],
  );
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): RealtimeValue {
  const value = useContext(RealtimeContext);
  if (!value) throw new Error('RealtimeProvider missing');
  return value;
}
