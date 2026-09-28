import { formatStake, REPORT_REASON_RU, type PlayerCardDto, type ReportReasonDto, type SendRequestResult } from '@arena/shared';
import { Avatar, BottomSheet, Button, Icon, RatingBadge, Skeleton } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ACHIEVEMENT_ICON } from '../../lib/achievements.js';
import { ringOf } from '../../lib/cosmetics.js';
import { ApiError, api } from '../../lib/api.js';
import { useToast } from '../../toast.js';

/**
 * Tap on a portrait at the table: who this is (this season and overall), their badges,
 * «В друзья», «Пожаловаться» and a label only I can see.
 */
export function PlayerSheet({ userId, gameId, onClose, onNote }: { userId: string | null; gameId?: string; onClose: () => void; onNote: (userId: string, note: string | null) => void }) {
  const toast = useToast();
  const [card, setCard] = useState<PlayerCardDto | null>(null);
  const [mode, setMode] = useState<'card' | 'note' | 'report'>('card');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCard(null);
    setMode('card');
    if (!userId) return;
    let live = true;
    api<PlayerCardDto>(`/players/${userId}/card`)
      .then((c) => live && setCard(c))
      .catch((e: unknown) => {
        toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
        onClose();
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');

  const addFriend = async () => {
    if (!card) return;
    setBusy(true);
    try {
      const { status } = await api<SendRequestResult>('/friends/requests', { method: 'POST', body: { userId: card.id } });
      const relation = status === 'friends' || status === 'already_friends' ? 'friend' : 'outgoing';
      setCard({ ...card, relation });
      toast(relation === 'friend' ? 'Теперь вы друзья' : 'Заявка отправлена', 'success');
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const saveNote = async (text = draft) => {
    if (!card) return;
    setBusy(true);
    try {
      const { note } = await api<{ note: string | null }>(`/players/${card.id}/note`, { method: 'PUT', body: { text } });
      setCard({ ...card, note });
      onNote(card.id, note);
      setMode('card');
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const report = async (reason: ReportReasonDto) => {
    if (!card) return;
    setBusy(true);
    try {
      await api(`/players/${card.id}/report`, { method: 'POST', body: { reason, ...(gameId ? { gameId } : {}) } });
      toast('Жалоба отправлена модераторам', 'success');
      setMode('card');
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const title = mode === 'report' ? 'Пожаловаться' : mode === 'note' ? 'Метка' : '';
  return (
    <BottomSheet open={userId !== null} title={title} onClose={onClose}>
      {!card ? (
        <div className="app-stack" aria-busy="true">
          <Skeleton height={72} radius={16} />
          <Skeleton height={120} radius={16} />
        </div>
      ) : mode === 'report' ? (
        <div className="app-list">
          <p className="app-muted">На что жалуетесь? Модераторы проверят партии {card.name}.</p>
          {(Object.keys(REPORT_REASON_RU) as ReportReasonDto[]).map((r) => (
            <Button key={r} block variant="ghost" disabled={busy} onClick={() => void report(r)}>
              {REPORT_REASON_RU[r]}
            </Button>
          ))}
          <Button block variant="ghost" onClick={() => setMode('card')}>Отмена</Button>
        </div>
      ) : mode === 'note' ? (
        <form
          className="app-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void saveNote();
          }}
        >
          <p className="app-muted">Метку видите только вы — например, «сильный» или «тянет время».</p>
          <input className="app-input" autoFocus maxLength={40} placeholder="Метка" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="app-row">
            <Button type="submit" loading={busy}>Сохранить</Button>
            {card.note && (
              <Button type="button" variant="ghost" disabled={busy} onClick={() => void saveNote('')}>
                Удалить
              </Button>
            )}
          </div>
        </form>
      ) : (
        <div className="player-card">
          <div className="player-card__head">
            <Avatar id={card.id} name={card.name} photoUrl={card.photoUrl} size={72} ring={ringOf(card.frame)} crown={Boolean(card.crown)} />
            <div className="player-card__who">
              <strong>{card.name}</strong>
              {card.username && <span className="app-muted">@{card.username}</span>}
              <RatingBadge rating={card.rating} />
              <button type="button" className="player-card__note" onClick={() => (setDraft(card.note ?? ''), setMode('note'))}>
                {card.note ? (
                  <>
                    <Icon name="star" size={14} /> {card.note}
                  </>
                ) : (
                  '+ добавить метку'
                )}
              </button>
            </div>
          </div>

          <table className="player-card__stats">
            <thead>
              <tr>
                <th />
                <th>{card.season ? 'В сезоне' : 'Сезон'}</th>
                <th>Всего</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Рейтинг</th>
                <td>{card.season ? card.season.rating.toLocaleString('ru-RU') : '—'}</td>
                <td>{card.total.rating.toLocaleString('ru-RU')}</td>
              </tr>
              <tr>
                <th>Выигрыш</th>
                <td>{card.season ? formatStake(card.season.winnings) : '—'}</td>
                <td>{formatStake(card.total.winnings)}</td>
              </tr>
              <tr>
                <th>Победы</th>
                <td>{card.season ? card.season.wins : '—'}</td>
                <td>
                  {card.total.wins} <small>из {card.total.games}</small>
                </td>
              </tr>
            </tbody>
          </table>

          {card.achievements.length > 0 && (
            <div className="player-card__badges" aria-label="Достижения">
              {card.achievements.map((a) => (
                <span key={a.key} className="player-card__badge" title={a.title}>
                  <Icon name={ACHIEVEMENT_ICON[a.icon] ?? 'star'} size={20} />
                </span>
              ))}
            </div>
          )}

          <div className="player-card__actions">
            {card.relation === 'none' ? (
              <Button icon="userPlus" loading={busy} onClick={() => void addFriend()}>В друзья</Button>
            ) : (
              <Button variant="ghost" disabled>
                {card.relation === 'friend' ? 'Друг' : card.relation === 'incoming' ? 'Ждёт вашего ответа' : 'Заявка отправлена'}
              </Button>
            )}
            <Button variant="danger" icon="flag" onClick={() => setMode('report')}>Пожаловаться</Button>
          </div>
        </div>
      )}
    </BottomSheet>
  );
}
