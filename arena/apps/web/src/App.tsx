import { Button, EmptyState, NavigationBar, type NavItem } from '@arena/ui';
import { lazy, Suspense, useState } from 'react';
import { NavigationProvider, useNav, type Page, type Tab } from './navigation.js';
import { HomeScreen } from './screens/HomeScreen.js';
import { SessionProvider, useSession } from './session.js';
import { ToastProvider, useToast } from './toast.js';
import { RealtimeProvider, useRealtime } from './realtime.js';
import { RoomScreen } from './screens/RoomScreen.js';
import { ApiError, api } from './lib/api.js';
import { parseRoomStartParam, type MyRoomDto } from '@arena/shared';
import { BottomSheet } from '@arena/ui';
import { useEffect, useRef } from 'react';
import { ScreenFallback } from './screens/common.js';

// Home ships in the main bundle; everything else loads on first visit.
const GamesScreen = lazy(() => import('./screens/GamesScreen.js'));
const TournamentsScreen = lazy(() => import('./screens/TournamentsScreen.js'));
const FriendsScreen = lazy(() => import('./screens/FriendsScreen.js'));
const MoreScreen = lazy(() => import('./screens/MoreScreen.js'));
const ProfileScreen = lazy(() => import('./screens/ProfileScreen.js'));
const AchievementsScreen = lazy(() => import('./screens/AchievementsScreen.js'));
const ItemsScreen = lazy(() => import('./screens/ItemsScreen.js'));
const RulesScreen = lazy(() => import('./screens/RulesScreen.js'));
const ServersScreen = lazy(() => import('./screens/ServersScreen.js'));
const SoonScreen = lazy(() => import('./screens/SoonScreen.js'));
const LeaderboardScreen = lazy(() => import('./screens/LeaderboardScreen.js'));
const CreateGameScreen = lazy(() => import('./screens/CreateGameScreen.js'));
const SettingsScreen = lazy(() => import('./screens/SettingsScreen.js'));
// The table is the most important screen: it loads as soon as the app starts, not on first use.
const gameModule = import('./screens/game/GameScreen.js');
const GameScreen = lazy(() => gameModule.then((m) => ({ default: m.GameScreen })));

const TABS: NavItem<Tab>[] = [
  { key: 'home', label: 'Профиль', icon: 'user' },
  { key: 'games', label: 'Игры', icon: 'cards' },
  { key: 'tournaments', label: 'Турниры', icon: 'trophy' },
  { key: 'friends', label: 'Друзья', icon: 'users' },
  { key: 'more', label: 'Ещё', icon: 'more' },
];

function TabScreen({ tab }: { tab: Tab }) {
  switch (tab) {
    case 'home':
      return <HomeScreen />;
    case 'games':
      return <GamesScreen />;
    case 'tournaments':
      return <TournamentsScreen />;
    case 'friends':
      return <FriendsScreen />;
    case 'more':
      return <MoreScreen />;
  }
}

function PageScreen({ page }: { page: Page }) {
  switch (page) {
    case 'create':
      return <CreateGameScreen />;
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
      return <SoonScreen title="Новости" text="Здесь будут обновления Арены, турниры и события." />;
    case 'settings':
      return <SettingsScreen />;
  }
}

function Shell() {
  const { tab, stack, setTab } = useNav();
  const { room, game, result } = useRealtime();
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
      </main>
    );
  }
  return (
    <>
      {passwordPrompt}
      <main className="app-screen" key={page ?? tab}>
        <Suspense fallback={<ScreenFallback />}>{page ? <PageScreen page={page} /> : <TabScreen tab={tab} />}</Suspense>
      </main>
      <NavigationBar items={TABS} active={tab} onSelect={setTab} />
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
  const startParam = state.status === 'ready' ? state.startParam : null;

  useEffect(() => {
    const link = parseRoomStartParam(startParam);
    if (!link || handled.current) return;
    handled.current = true;
    api<MyRoomDto>(`/rooms/${link.roomId}/join`, { method: 'POST', body: link.invite ? { invite: link.invite } : {} })
      .then(enterRoom)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === 'WRONG_PASSWORD') setNeedPassword(link.roomId);
        else toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
      });
  }, [startParam, enterRoom, toast]);

  return needPassword ? <PasswordPrompt roomId={needPassword} onDone={() => setNeedPassword(null)} /> : null;
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

function DevLogin() {
  const { devLogin } = useSession();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const login = (id: number, name: string) => {
    setBusy(true);
    devLogin(id, name).catch(() => setFailed(true)).finally(() => setBusy(false));
  };
  // Development only: ?dev=3 signs in as «Игрок 3» — handy for testing tables of up to six.
  const auto = import.meta.env.DEV ? Number(new URLSearchParams(location.search).get('dev')) : 0;
  useEffect(() => {
    if (auto > 0) login(1000 + auto, `Игрок ${auto}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto]);
  return (
    <div className="app-center">
      <EmptyState
        icon="lock"
        title="Откройте игру из Telegram"
        text={failed ? 'Локальный вход выключен на сервере (DEV_AUTH).' : 'Арена работает внутри бота Маруська. Для разработки можно войти тестовым игроком.'}
        action={
          import.meta.env.DEV ? (
            <div className="app-row">
              <Button size="sm" loading={busy} onClick={() => login(1001, 'Игрок 1')}>Игрок 1</Button>
              <Button size="sm" variant="ghost" loading={busy} onClick={() => login(1002, 'Игрок 2')}>Игрок 2</Button>
            </div>
          ) : undefined
        }
      />
    </div>
  );
}

function Gate() {
  const { state, retry } = useSession();
  if (state.status === 'loading') return <ScreenFallback fullscreen />;
  if (state.status === 'outside-telegram') return <DevLogin />;
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
