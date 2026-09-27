import { Button, EmptyState, NavigationBar, type NavItem } from '@arena/ui';
import { lazy, Suspense, useState } from 'react';
import { NavigationProvider, useNav, type Page, type Tab } from './navigation.js';
import { HomeScreen } from './screens/HomeScreen.js';
import { SessionProvider, useSession } from './session.js';
import { ToastProvider } from './toast.js';
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
      return <SoonScreen title="Доска почёта" text="Лучшие игроки дня, недели и всех времён появятся вместе с первыми рейтинговыми партиями." />;
    case 'news':
      return <SoonScreen title="Новости" text="Здесь будут обновления Арены, турниры и события." />;
    case 'settings':
      return <SoonScreen title="Настройки" text="Звук, вибрация, рубашка карт и стол — на следующем этапе." />;
  }
}

function Shell() {
  const { tab, stack, setTab } = useNav();
  const page = stack[stack.length - 1];
  return (
    <>
      <main className="app-screen" key={page ?? tab}>
        <Suspense fallback={<ScreenFallback />}>{page ? <PageScreen page={page} /> : <TabScreen tab={tab} />}</Suspense>
      </main>
      <NavigationBar items={TABS} active={tab} onSelect={setTab} />
    </>
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
    <NavigationProvider>
      <Shell />
    </NavigationProvider>
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
