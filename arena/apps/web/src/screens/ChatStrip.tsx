import type { ChatMessageDto, ChatStateDto } from '@arena/shared';
import { Icon } from '@arena/ui';
import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { chatHasNew } from '../lib/chat.js';
import { useNav } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';

const SHOWN = 2;

/** The common chat on the home screen: the latest messages, live; a tap opens the chat. */
export function ChatStrip() {
  const me = useMe();
  const { socket } = useRealtime();
  const { push } = useNav();
  const [messages, setMessages] = useState<ChatMessageDto[] | null>(null);
  const [online, setOnline] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<ChatStateDto>(`/chat?limit=${SHOWN}`)
        .then((s) => {
          if (!alive) return;
          setMessages(s.messages);
          setOnline(s.online);
        })
        .catch(() => undefined);
    const offMsg = socket.onMessage((m) => {
      if (m.type === 'CHAT_MESSAGE') setMessages((list) => [...(list ?? []).filter((x) => x.id !== m.message.id), m.message].slice(-SHOWN));
      else if (m.type === 'CHAT_DELETED') void load();
    });
    const offOpen = socket.onOpen(() => {
      void socket.send({ type: 'CHAT_SUBSCRIBE' });
      void load();
    });
    return () => {
      alive = false;
      offMsg();
      offOpen();
      void socket.send({ type: 'CHAT_UNSUBSCRIBE' });
    };
  }, [socket]);

  const latest = messages?.at(-1)?.createdAt ?? me.chatLastAt;
  const fresh = chatHasNew(latest ?? null);

  return (
    <button type="button" className={`chat-strip${fresh ? ' chat-strip--fresh' : ''}`} onClick={() => push('chat')}>
      <span className="chat-strip__head">
        <Icon name="chat" size={18} />
        <b>Общий чат</b>
        {online !== null && <small>· в Арене {online}</small>}
        {fresh && <i className="chat-strip__new">новое</i>}
        <span className="chat-strip__arrow" aria-hidden="true">›</span>
      </span>
      {messages === null ? (
        <span className="chat-strip__line chat-strip__line--muted">Загрузка…</span>
      ) : messages.length === 0 ? (
        <span className="chat-strip__line chat-strip__line--muted">Пока тихо — напишите первым</span>
      ) : (
        messages.map((m) => (
          <span key={m.id} className="chat-strip__line">
            <b>{m.user.id === me.id ? 'Вы' : m.user.name}:</b> {m.text}
          </span>
        ))
      )}
    </button>
  );
}
