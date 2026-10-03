import { Button, EmptyState, NavigationBar, preloadCardArt, type NavItem } from '@arena/ui';
import { backOf } from './lib/cosmetics.js';
import { lazy, Suspense, useState } from 'react';
import { NavigationProvider, useNav, type Page, type Tab } from './navigation.js';
import { HomeScreen } from './screens/HomeScreen.js';
import { SessionProvider, useSession } from './session.js';
import { ToastProvider, useToast } from './toast.js';
import { RealtimeProvider, useRealtime } from './realtime.js';
import { RoomScreen } from './screens/RoomScreen.js';
import { AnnouncementPopup } from './screens/AnnouncementPopup.js';
import { ApiError, api } from './lib/api.js';
import { parseRoomStartParam, type MyRoomDto, type ReferralInfoDto } from '@arena/shared';
import { BottomSheet } from '@arena/ui';
import { useEffect, useRef } from 'react';
import { ScreenFallback } from './screens/common.js';
import { AppLogin } from './screens/AppLogin.js';
import { ConnectionBanner } from './screens/ConnectionBanner.js';

// Home ships in the main bundle; everything else loads on first visit.
const LobbyScreen = lazy(() => import('./screens/LobbyScreen.js'));
const FiltersScreen = lazy(() => import('./screens/FiltersScreen.js'));
const TournamentsScreen = lazy(() => import('./screens/TournamentsScreen.js'));
const FriendsScreen = lazy(() => import('./screens/FriendsScreen.js'));
const ProfileScreen = lazy(() => import('./screens/ProfileScreen.js'));
const AchievementsScreen = lazy(() => import('./screens/AchievementsScreen.js'));
const ItemsScreen = lazy(() => import('./screens/ItemsScreen.js'));
const RulesScreen = lazy(() => import('./screens/RulesScreen.js'));
const ServersScreen = lazy(() => import('./screens/ServersScreen.js'));
const NewsScreen = lazy(() => import('./screens/NewsScreen.js'));
const LeaderboardScreen = lazy(() => import('./screens/LeaderboardScreen.js'));
const CreateGameScreen = lazy(() => import('./screens/CreateGameScreen.js'));
const SettingsScreen = lazy(() => import('./screens/SettingsScreen.js'));
const OwnerScreen = lazy(() => import('./screens/OwnerScreen.js'));
const InviteScreen = lazy(() => import('./screens/InviteScreen.js'));
const DailyScreen = lazy(() => import('./screens/DailyScreen.js'));
const ChatScreen = lazy(() => import('./screens/ChatScreen.js'));
const PlayerScreen = lazy(() => import('./screens/player/PlayerScreen.js'));
// The table is the most important screen: it loads as soon as the app starts, not on first use.
const gameModule = import('./screens/game/GameScreen.js');
const GameScreen = lazy(() => gameModule.then((m) => ({ default: m.GameScreen })));

const TABS: NavItem<Tab>[] = [
  { key: 'home', label: 'Профиль', icon: 'user' },
  { key: 'open', label: 'Открытые', icon: 'cards' },
  { key: 'private', label: 'Приватные', icon: 'lock' },
  { key: 'create', label: 'Создать игру', icon: 'plus', accent: true },
];

function TabScreen({ tab }: { tab: Tab }) {
  switch (tab) {
    case 'home':
      return <HomeScreen />;
    case 'open':
      return <LobbyScreen scope="open" />;
    case 'private':
      return <LobbyScreen scope="private" />;
    case 'create':
      return <CreateGameScreen />;
  }
}

function PageScreen({ page }: { page: Page }) {
  switch (page) {
    case 'filters':
      return <FiltersScreen />;
    case 'tournaments':
      return <TournamentsScreen />;
    case 'friends':
      return <FriendsScreen />;
    case 'profile':
      return <ProfileScreen />;
    case 'achievements':
      return <AchievementsScreen />;
    case 'items':
      return <ItemsScreen />;
    case 'rules':
      return <RulesScreen />;
    case 'servers':
      return <ServersScreen />;
    case 'leaderboard':
      return <LeaderboardScreen />;
    case 'news':
      return <NewsScreen />;
    case 'settings':
      return <SettingsScreen />;
    case 'owner':
      return <OwnerScreen />;
    case 'player':
      return <PlayerScreen />;
    case 'invite':
      return <InviteScreen />;
    case 'daily':
      return <DailyScreen />;
    case 'chat':
      return <ChatScreen />;
  }
}

function Shell() {
  const { tab, stack, setTab } = useNav();
  const { room, game, result, requestCount } = useRealtime();
  const { state: session } = useSession();
  const myBack = session.status === 'ready' ? session.me.equipped.cardBack : null;
  // Card pictures are fetched and decoded in the lobby, well before the first deal.
  useEffect(() => {
    if (session.status === 'ready') preloadCardArt(backOf(myBack));
  }, [session.status, myBack]);
  const items = TABS.map((t) => (t.key === 'home' ? { ...t, badge: requestCount } : t));
  const page = stack[stack.length - 1];
  const passwordPrompt = useDeepLink();

  // During a game (and on its result screen) the table owns the whole screen.
  if (game && (game.state.status === 'playing' || result)) {
    return (
      <Suspense fallback={<ScreenFallback fullscreen />}>
        <GameScreen game={game} />
      </Suspense>
    );
  }
  if (room && room.status === 'waiting') {
    return (
      <main className="app-screen app-screen--full">
        <RoomScreen room={room} />
        <InviteSheet />
      </main>
    );
  }
  return (
    <>
      {passwordPrompt}
      <InviteSheet />
      <AnnouncementPopup />
      <main className="app-screen" key={page ?? tab}>
        <Suspense fallback={<ScreenFallback />}>{page ? <PageScreen page={page} /> : <TabScreen tab={tab} />}</Suspense>
      </main>
      <NavigationBar items={items} active={tab} onSelect={setTab} />
    </>
  );
}

/** t.me/<bot>/<app>?startapp=game_<room>[_<invite>] opens the room right away; asks for a password if needed. */
function useDeepLink() {
  const { state } = useSession();
  const { enterRoom } = useRealtime();
  const toast = useToast();
  const handled = useRef(false);
  const [needPassword, setNeedPassword] = useState<string | null>(null);
  // From a t.me link Telegram passes start_param; an invite button from the bot opens the arena
  // directly with ?start=… in the address instead.
  const startParam =
    state.status === 'ready' ? state.startParam ?? new URLSearchParams(window.location.search).get('start') : null;

  const { push } = useNav();
  useEffect(() => {
    if (startParam === 'friends' && !handled.current) {
      handled.current = true;
      push('friends');
      return;
    }
    if (startParam?.startsWith('ref_') && !handled.current) {
      // Came by a friend's invite: tell the newcomer what the first game with people brings.
      handled.current = true;
      api<ReferralInfoDto>('/referrals')
        .then((info) => {
          if (info.invitedBy?.pending && info.invitedBy.coins > 0) {
            toast(`${info.invitedBy.name} пригласил(а) вас в Арену! Сыграйте первую партию с живыми соперниками — получите ${info.invitedBy.coins} монет 🎁`, 'success');
          }
        })
        .catch(() => undefined);
      return;
    }
    const link = parseRoomStartParam(startParam);
    if (!link || handled.current) return;
    handled.current = true;
    api<MyRoomDto>(`/rooms/${link.roomId}/join`, { method: 'POST', body: link.invite ? { invite: link.invite } : {} })
      .then(enterRoom)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === 'WRONG_PASSWORD') setNeedPassword(link.roomId);
        else toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
      });
  }, [startParam, enterRoom, toast, push]);

  return needPassword ? <PasswordPrompt roomId={needPassword} onDone={() => setNeedPassword(null)} /> : null;
}

/** «Друг зовёт вас в игру» — shown over any screen while not already at a table. */
function InviteSheet() {
  const { invites, dismissInvite, enterRoom, room } = useRealtime();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const current = invites[0];
  if (!current || (room && room.id === current.room.id)) return null;
  const accept = () => {
    setBusy(true);
    api<MyRoomDto>(`/rooms/${current.room.id}/join`, { method: 'POST', body: { invite: current.invite } })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => {
        setBusy(false);
        dismissInvite(current.room.id);
      });
  };
  return (
    <BottomSheet open title="Приглашение в игру" onClose={() => dismissInvite(current.room.id)}>
      <div className="app-stack">
        <p>
          <strong>{current.from.name}</strong> зовёт вас за стол: {current.room.settings.stake > 0 ? `ставка ${current.room.settings.stake}` : 'тренировочный стол'}, игроков{' '}
          {current.room.seats.length}/{current.room.settings.players}.
        </p>
        <Button block variant="gold" loading={busy} onClick={accept}>
          Играть
        </Button>
        <Button block variant="ghost" onClick={() => dismissInvite(current.room.id)}>
          Не сейчас
        </Button>
      </div>
    </BottomSheet>
  );
}

function PasswordPrompt({ roomId, onDone }: { roomId: string; onDone: () => void }) {
  const { enterRoom } = useRealtime();
  const toast = useToast();
  const [password, setPassword] = useState('');
  const submit = () =>
    api<MyRoomDto>(`/rooms/${roomId}/join`, { method: 'POST', body: { password } })
      .then((mine) => (enterRoom(mine), onDone()))
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'));
  return (
    <BottomSheet open title="Приватная игра" onClose={onDone}>
      <div className="app-stack">
        <input className="app-input" type="password" placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button block onClick={() => void submit()}>Войти</Button>
      </div>
    </BottomSheet>
  );
}

/** Outside Telegram: sign in by confirming in the bot (the installed app «Арена»). */
function SignedOut() {
  const { devLogin } = useSession();
  const [busy, setBusy] = useState(false);
  const login = (id: number, name: string) => {
    setBusy(true);
    devLogin(id, name).catch(() => undefined).finally(() => setBusy(false));
  };
  // Development only: ?dev=3 signs in as «Игрок 3» — handy for testing tables of up to six.
  const auto = import.meta.env.DEV ? Number(new URLSearchParams(location.search).get('dev')) : 0;
  useEffect(() => {
    if (auto > 0) login(1000 + auto, `Игрок ${auto}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto]);
  return (
    <AppLogin
      dev={
        import.meta.env.DEV ? (
          <div className="app-row">
            <Button size="sm" loading={busy} onClick={() => login(1001, 'Игрок 1')}>Игрок 1</Button>
            <Button size="sm" variant="ghost" loading={busy} onClick={() => login(1002, 'Игрок 2')}>Игрок 2</Button>
          </div>
        ) : undefined
      }
    />
  );
}

function Gate() {
  const { state, retry } = useSession();
  if (state.status === 'loading') return <ScreenFallback fullscreen />;
  if (state.status === 'outside-telegram') return <SignedOut />;
  if (state.status === 'error') {
    return (
      <div className="app-center">
        <EmptyState
          icon={state.error.code === 'NO_CONNECTION' ? 'wifiOff' : 'lock'}
          title={state.error.code === 'NO_CONNECTION' ? 'Нет соединения' : 'Не удалось войти'}
          text={state.error.message}
          action={<Button onClick={retry}>Повторить</Button>}
        />
      </div>
    );
  }
  return (
    <RealtimeProvider>
      <NavigationProvider>
        <Shell />
        <ConnectionBanner />
      </NavigationProvider>
    </RealtimeProvider>
  );
}

export function App() {
  return (
    <ToastProvider>
      <SessionProvider>
        <Gate />
      </SessionProvider>
    </ToastProvider>
  );
}
