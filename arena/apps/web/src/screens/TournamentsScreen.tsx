import type { TournamentDetailDto, TournamentDto } from '@arena/shared';
import { Avatar, Badge, Balance, BottomSheet, Button, EmptyState, Panel, Tabs } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const STATUS = {
  ANNOUNCED: ['cyan', 'Скоро'],
  REGISTRATION: ['green', 'Регистрация'],
  RUNNING: ['violet', 'Идёт'],
  FINISHED: ['muted', 'Завершён'],
  CANCELLED: ['red', 'Отменён'],
} as const;

const when = (iso: string) => new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function roundName(round: number, rounds: number): string {
  const left = rounds - round;
  return left === 0 ? 'Финал' : left === 1 ? 'Полуфинал' : left === 2 ? 'Четвертьфинал' : `Раунд ${round}`;
}

export default function TournamentsScreen() {
  const [tab, setTab] = useState<'active' | 'finished'>('active');
  const [openId, setOpenId] = useState<string | null>(null);
  const query = useQuery<TournamentDto[]>(`/tournaments?status=${tab}`);
  return (
    <div className="app-stack">
      <ScreenHeader title="Турниры" subtitle="Игра на выбывание один на один" />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'active', label: 'Активные' }, { value: 'finished', label: 'Завершённые' }]} />
      <QueryView query={query}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState icon="trophy" title="Турниров пока нет" text="Новые турниры объявляются в боте Маруська." />
          ) : (
            <div className="app-list">
              {list.map((t) => {
                const [tone, label] = STATUS[t.status];
                return (
                  <Panel key={t.id} glow={t.joined ? 'gold' : t.status === 'RUNNING' ? 'violet' : 'none'} className="tour-card" role="button" tabIndex={0} onClick={() => setOpenId(t.id)}>
                    <div className="app-row app-row--between">
                      <strong>{t.title}</strong>
                      <Badge tone={tone}>{label}</Badge>
                    </div>
                    <div className="tour-card__grid">
                      <span>Призовой фонд</span>
                      <Balance kind="credits" value={t.prizePool} compact />
                      <span>Взнос</span>
                      {t.entryFee ? <Balance kind="credits" value={t.entryFee} compact /> : <strong>бесплатно</strong>}
                      <span>Участники</span>
                      <strong>{t.players}/{t.maxPlayers}</strong>
                      <span>Начало</span>
                      <strong>{when(t.startsAt)}</strong>
                    </div>
                    <span className="app-muted">{t.modes.join(' · ')}</span>
                    {t.joined && <Badge tone="gold">Вы участвуете</Badge>}
                  </Panel>
                );
              })}
            </div>
          )
        }
      </QueryView>
      <BottomSheet open={openId !== null} title="Турнир" onClose={() => (setOpenId(null), query.reload())}>
        {openId && <TournamentDetail id={openId} />}
      </BottomSheet>
    </div>
  );
}

function TournamentDetail({ id }: { id: string }) {
  const query = useQuery<TournamentDetailDto>(`/tournaments/${id}`);
  const me = useMe();
  const { refreshMe } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const act = async (path: string, done: string) => {
    setBusy(true);
    try {
      await api(path, { method: 'POST' });
      query.reload();
      await refreshMe();
      toast(done, 'success');
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <QueryView query={query}>
      {(t) => {
        const rounds = [...new Set(t.matches.map((m) => m.round))].sort((a, b) => a - b);
        return (
          <div className="app-stack">
            <h3>{t.title}</h3>
            <p className="app-muted">
              {t.modes.join(' · ')} · старт {when(t.startsAt)} · {t.players}/{t.maxPlayers} игроков
            </p>
            <Panel className="tour-prizes">
              <strong>Призы · фонд <Balance kind="credits" value={t.prizePool} /></strong>
              {t.prizes.map((p, i) => (
                <div key={i} className="app-row app-row--between">
                  <span>{i + 1} место</span>
                  <Balance kind="credits" value={p} />
                </div>
              ))}
            </Panel>

            {t.status === 'REGISTRATION' &&
              (t.joined ? (
                <Button block variant="ghost" loading={busy} onClick={() => void act(`/tournaments/${id}/unregister`, 'Участие отменено, взнос возвращён')}>
                  Отменить участие
                </Button>
              ) : (
                <Button block variant="gold" loading={busy} disabled={t.players >= t.maxPlayers || me.wallet.credits < t.entryFee} onClick={() => void act(`/tournaments/${id}/register`, 'Вы в турнире!')}>
                  Участвовать{t.entryFee ? ` · ${t.entryFee}` : ''}
                </Button>
              ))}
            {t.status === 'RUNNING' && t.joined && <p className="app-muted">Когда начнётся ваш матч, стол откроется сам — нажмите «Готов» в течение 90 секунд.</p>}

            {rounds.map((round) => (
              <section key={round} className="app-stack">
                <h4 className="app-section">{roundName(round, t.rounds)}</h4>
                {t.matches
                  .filter((m) => m.round === round)
                  .map((m) => (
                    <div key={m.id} className="tour-match">
                      {[m.a, m.b].map((p, i) =>
                        p ? (
                          <div key={p.id} className={`tour-match__side${m.winnerId === p.id ? ' tour-match__side--win' : m.winnerId ? ' tour-match__side--out' : ''}`}>
                            <Avatar id={p.id} name={p.name} photoUrl={p.photoUrl} size={26} />
                            <span>{p.id === me.id ? 'Вы' : p.name}</span>
                          </div>
                        ) : (
                          <div key={`bye${i}`} className="tour-match__side tour-match__side--out">
                            <span className="app-muted">проход без игры</span>
                          </div>
                        ),
                      )}
                      <span className="tour-match__state">{m.status === 'PLAYING' ? 'идёт' : m.decidedBy === 'no_show' ? 'неявка' : m.decidedBy === 'forfeit' ? 'сдался' : ''}</span>
                    </div>
                  ))}
              </section>
            ))}

            {t.entrants.some((e) => e.place) && (
              <section className="app-stack">
                <h4 className="app-section">Итоги</h4>
                {t.entrants
                  .filter((e) => e.place)
                  .map((e) => (
                    <div key={e.id} className="app-row app-row--between">
                      <span>{e.place}. {e.id === me.id ? 'Вы' : e.name}</span>
                      {e.prize ? <Balance kind="credits" value={e.prize} /> : <span className="app-muted">—</span>}
                    </div>
                  ))}
              </section>
            )}
          </div>
        );
      }}
    </QueryView>
  );
}
