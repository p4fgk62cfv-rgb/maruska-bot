import { CHAT, type ChatMessageDto, type ChatStateDto } from '@arena/shared';
import { Avatar, BottomSheet, Button, EmptyState, Icon } from '@arena/ui';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { markChatSeen } from '../lib/chat.js';
import { safeStorage } from '../lib/hooks.js';
import { haptic } from '../lib/telegram.js';
import { useNav } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenFallback, ScreenHeader } from './common.js';

const HIDDEN_KEY = 'arena.chatHidden';

function timeOf(iso: string): string {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  return today
    ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/**
 * The part of the screen above the phone keyboard. iPhone keeps the page height when the
 * keyboard opens and scrolls the page instead; the chat follows the visible area, so the
 * message field stays right on top of the keyboard and nothing jumps.
 */
function useVisibleArea(): { top: number; height: number; keyboard: boolean } {
  const read = () => {
    const vv = typeof window !== 'undefined' ? window.visualViewport : null;
    const height = vv?.height ?? window.innerHeight;
    return { top: vv?.offsetTop ?? 0, height, keyboard: window.innerHeight - height > 120 };
  };
  const [area, setArea] = useState(read);
  useEffect(() => {
    const vv = window.visualViewport;
    const update = () => setArea(read());
    vv?.addEventListener('resize', update);
    vv?.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    return () => {
      vv?.removeEventListener('resize', update);
      vv?.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);
  return area;
}

/** «Общий чат»: one room for the whole Arena. */
export default function ChatScreen() {
  const me = useMe();
  const { socket } = useRealtime();
  const { openPlayer } = useNav();
  const toast = useToast();
  const area = useVisibleArea();
  const listRef = useRef<HTMLDivElement>(null);
  const nearBottom = () => {
    const el = listRef.current;
    return !el || el.scrollTop + el.clientHeight >= el.scrollHeight - 160;
  };
  const toBottom = () => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };
  const [state, setState] = useState<ChatStateDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [picked, setPicked] = useState<ChatMessageDto | null>(null);
  const [hidden, setHidden] = useState<string[]>(() => safeStorage.get<string[]>(HIDDEN_KEY, []));
  const stick = useRef(true);
  const firstLoad = useRef(true);

  const load = useCallback(() => {
    api<ChatStateDto>('/chat')
      .then((fresh) => {
        stick.current = firstLoad.current || nearBottom();
        firstLoad.current = false;
        setState(fresh);
        setError(null);
        markChatSeen(fresh.messages.at(-1)?.createdAt ?? null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Не удалось загрузить чат'));
  }, []);

  // Live: subscribe on every (re)connect and reload what was missed while offline.
  useEffect(() => {
    const offMsg = socket.onMessage((m) => {
      if (m.type === 'CHAT_MESSAGE') {
        stick.current = nearBottom() || m.message.user.id === me.id;
        setState((s) => (s && !s.messages.some((x) => x.id === m.message.id) ? { ...s, messages: [...s.messages, m.message] } : s));
        markChatSeen(m.message.createdAt);
      } else if (m.type === 'CHAT_DELETED') {
        setState((s) => (s ? { ...s, messages: s.messages.filter((x) => !m.ids.includes(x.id)) } : s));
      }
    });
    const offOpen = socket.onOpen(() => {
      void socket.send({ type: 'CHAT_SUBSCRIBE' });
      load();
    });
    return () => {
      offMsg();
      offOpen();
      void socket.send({ type: 'CHAT_UNSUBSCRIBE' });
    };
  }, [socket, load, me.id]);

  useLayoutEffect(() => {
    if (stick.current) toBottom();
  }, [state?.messages.length, area.height]);

  const older = () => {
    const first = state?.messages[0];
    if (!first) return;
    setLoadingOlder(true);
    const height = listRef.current?.scrollHeight ?? 0;
    api<ChatStateDto>(`/chat?before=${first.id}`)
      .then((page) => {
        stick.current = false;
        setState((s) => (s ? { ...s, more: page.more, messages: [...page.messages, ...s.messages.filter((m) => !page.messages.some((p) => p.id === m.id))] } : s));
        // Keep the reader where they were: the new messages appear above.
        requestAnimationFrame(() => {
          const el = listRef.current;
          if (el) el.scrollTop += el.scrollHeight - height;
        });
      })
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setLoadingOlder(false));
  };

  const send = () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    api<ChatMessageDto>('/chat', { method: 'POST', body: { text: value } })
      .then((message) => {
        haptic.tap();
        setText('');
        stick.current = true;
        setState((s) => (s && !s.messages.some((x) => x.id === message.id) ? { ...s, messages: [...s.messages, message] } : s));
      })
      .catch((e: unknown) => {
        toast(e instanceof ApiError ? e.message : 'Не отправлено', 'error');
        if (e instanceof ApiError && (e.code === 'CHAT_MUTED' || e.code === 'CHAT_NEED_GAME')) load();
      })
      .finally(() => setSending(false));
  };

  const toggleHidden = (userId: string) => {
    const next = hidden.includes(userId) ? hidden.filter((id) => id !== userId) : [...hidden, userId];
    setHidden(next);
    safeStorage.set(HIDDEN_KEY, next);
    setPicked(null);
  };

  const act = (path: string, method: 'POST' | 'DELETE', body: object | undefined, done: string) => {
    setPicked(null);
    api(path, { method, body })
      .then(() => {
        haptic.success();
        toast(done, 'success');
      })
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'));
  };

  if (!state) {
    return (
      <div className="app-stack">
        <ScreenHeader title="Общий чат" />
        {error ? <EmptyState icon="close" title="Не удалось загрузить" text={error} action={<Button onClick={load}>Повторить</Button>} /> : <ScreenFallback />}
      </div>
    );
  }

  const visible = state.messages.filter((m) => !hidden.includes(m.user.id));
  const blocked = state.blocked;

  return (
    <div
      className={`chat-shell${area.keyboard ? ' chat-shell--keyboard' : ''}`}
      style={area.keyboard ? { top: area.top, height: area.height } : undefined}
    >
      <ScreenHeader title="Общий чат" subtitle={`Сейчас в Арене: ${state.online}`} />
      <div className="chat-scroll" ref={listRef}>
      {state.more && (
        <button type="button" className="chat-older" onClick={older} disabled={loadingOlder}>
          {loadingOlder ? 'Загружаю…' : 'Показать сообщения раньше'}
        </button>
      )}
      {visible.length === 0 ? (
        <EmptyState icon="chat" title="Пока тихо" text="Напишите первым: позовите соперников или поделитесь впечатлениями от партии." />
      ) : (
        <ol className="chat-list">
          {visible.map((m, i) => {
            const mine = m.user.id === me.id;
            const sameAuthor = visible[i - 1]?.user.id === m.user.id;
            return (
              <li key={m.id} className={`chat-msg${mine ? ' chat-msg--mine' : ''}${sameAuthor ? ' chat-msg--cont' : ''}`}>
                {!mine && (
                  <button type="button" className="chat-msg__avatar" onClick={() => openPlayer(m.user.id)} aria-label={m.user.name}>
                    {!sameAuthor && <Avatar id={m.user.id} name={m.user.name} photoUrl={m.user.photoUrl} size={34} />}
                  </button>
                )}
                <button type="button" className="chat-msg__bubble" onClick={() => setPicked(m)}>
                  {!mine && !sameAuthor && <strong className="chat-msg__name">{m.user.name}</strong>}
                  <span className="chat-msg__text">{m.text}</span>
                  <small className="chat-msg__time">{timeOf(m.createdAt)}</small>
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {hidden.length > 0 && <p className="chat-hidden-note">Скрыты сообщения игроков: {hidden.length}. Вернуть — в меню сообщения игрока.</p>}
      </div>

      <div className="chat-composer">
        {blocked ? (
          <p className="chat-composer__blocked">
            {blocked.reason === 'muted'
              ? `Модератор запретил вам писать в чат${blocked.until ? ` до ${new Date(blocked.until).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}` : ''}.`
              : 'Писать в чат можно после первой сыгранной партии — подойдёт и тренировочная с ботами.'}
          </p>
        ) : (
          <form
            className="chat-composer__form"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              className="chat-composer__input"
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, CHAT.maxLength))}
              placeholder="Сообщение для всех"
              enterKeyHint="send"
              maxLength={CHAT.maxLength}
              aria-label="Сообщение"
            />
            <button type="submit" className="chat-composer__send" disabled={!text.trim() || sending} aria-label="Отправить">
              {sending ? <span className="ui-spinner" /> : <Icon name="send" size={20} />}
            </button>
          </form>
        )}
      </div>

      <BottomSheet open={picked !== null} title={picked?.user.name ?? ''} onClose={() => setPicked(null)}>
        {picked && (
          <div className="chat-actions">
            <p className="chat-actions__quote">«{picked.text}»</p>
            <Button variant="ghost" block icon="user" onClick={() => (setPicked(null), openPlayer(picked.user.id))}>
              Профиль игрока
            </Button>
            {picked.user.id !== me.id && (
              <>
                <Button variant="ghost" block icon="flag" onClick={() => act(`/chat/${picked.id}/report`, 'POST', undefined, 'Жалоба отправлена модераторам')}>
                  Пожаловаться
                </Button>
                <Button variant="ghost" block icon="eye" onClick={() => toggleHidden(picked.user.id)}>
                  {hidden.includes(picked.user.id) ? 'Снова показывать его сообщения' : 'Скрыть сообщения этого игрока'}
                </Button>
              </>
            )}
            {state.moderator && (
              <>
                <h4 className="chat-actions__title">Модерация</h4>
                <Button variant="danger" block onClick={() => act(`/chat/${picked.id}`, 'DELETE', undefined, 'Сообщение удалено')}>
                  Удалить сообщение
                </Button>
                {picked.user.id !== me.id && (
                  <div className="chat-actions__mute">
                    {[
                      [1, '1 час'],
                      [24, '1 день'],
                      [168, '7 дней'],
                    ].map(([hours, label]) => (
                      <Button
                        key={label}
                        variant="ghost"
                        size="sm"
                        onClick={() => act('/chat/mute', 'POST', { userId: picked.user.id, hours, purge: true }, `Запрет писать: ${label}`)}
                      >
                        Запрет {label}
                      </Button>
                    ))}
                    <Button variant="ghost" size="sm" onClick={() => act('/chat/mute', 'POST', { userId: picked.user.id, hours: 0 }, 'Писать снова можно')}>
                      Снять запрет
                    </Button>
                  </div>
                )}
                <p className="chat-actions__hint">Запрет также удаляет его сообщения за последние сутки.</p>
              </>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
