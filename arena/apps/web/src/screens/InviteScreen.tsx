import type { ReferralInfoDto } from '@arena/shared';
import { Avatar, Badge, Balance, Button, EmptyState, Icon, Panel } from '@arena/ui';
import { haptic, tg } from '../lib/telegram.js';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const SHARE_TEXT = 'Го в дурака в Маруська Арене! Подкидной, переводной, турниры — прямо в Telegram 🃏';

/** «Пригласить друга»: my link, the reward for both and whom I already brought. */
export default function InviteScreen() {
  const query = useQuery<ReferralInfoDto>('/referrals');
  const toast = useToast();
  const { openPlayer } = useNav();

  const copy = (link: string) => {
    void navigator.clipboard
      ?.writeText(link)
      .then(() => {
        haptic.success();
        toast('Ссылка скопирована', 'success');
      })
      .catch(() => toast(link));
  };

  const share = (info: ReferralInfoDto) => {
    if (!info.link) return;
    haptic.tap();
    const text = info.enabled && info.inviteeCoins > 0 ? `${SHARE_TEXT}\nПо этой ссылке — ${info.inviteeCoins} монет в подарок 🎁` : SHARE_TEXT;
    const url = `https://t.me/share/url?url=${encodeURIComponent(info.link)}&text=${encodeURIComponent(text)}`;
    if (tg) tg.openTelegramLink(url);
    else copy(info.link);
  };

  return (
    <div className="app-stack">
      <ScreenHeader title="Пригласить друга" />
      <QueryView query={query}>
        {(info) => (
          <>
            <Panel glow="gold" className="invite-hero">
              <span className="invite-hero__icon">
                <Icon name="users" size={34} />
              </span>
              {info.enabled ? (
                <>
                  <strong className="invite-hero__title">Зовите друзей — получайте монеты</strong>
                  <div className="invite-hero__rewards">
                    <span>
                      <small>Вам</small>
                      <Balance kind="coins" value={info.referrerCoins} />
                    </span>
                    <span>
                      <small>Другу</small>
                      <Balance kind="coins" value={info.inviteeCoins} />
                    </span>
                  </div>
                  <span className="app-muted">Друг открывает Арену по вашей ссылке и играет первую партию с живыми соперниками — монеты получаете оба, а вы сразу становитесь друзьями.</span>
                </>
              ) : (
                <>
                  <strong className="invite-hero__title">Играйте вместе с друзьями</strong>
                  <span className="app-muted">Отправьте ссылку — друг сразу появится в вашем списке друзей.</span>
                </>
              )}
              {info.link ? (
                <div className="invite-hero__actions">
                  <Button variant="gold" block icon="share" onClick={() => share(info)}>
                    Пригласить
                  </Button>
                  <button type="button" className="invite-link" onClick={() => copy(info.link!)}>
                    <span>{info.link.replace(/^https:\/\//, '')}</span>
                    <Icon name="copy" size={16} />
                  </button>
                </div>
              ) : (
                <span className="app-muted">Ссылка появится, когда администратор подключит бота.</span>
              )}
            </Panel>

            {info.invitedBy && (
              <Panel className="invite-by">
                <Avatar id={info.invitedBy.id} name={info.invitedBy.name} photoUrl={info.invitedBy.photoUrl} size={40} />
                <div className="invite-by__body">
                  <span className="app-muted">Вас пригласил(а)</span>
                  <strong>{info.invitedBy.name}</strong>
                </div>
                {info.invitedBy.pending ? (
                  <Badge tone="gold">+{info.invitedBy.coins} после первой партии</Badge>
                ) : (
                  <Badge tone="green">+{info.invitedBy.coins} получено</Badge>
                )}
              </Panel>
            )}

            <div className="invite-stats">
              <Panel>
                <strong>{info.invited}</strong>
                <span className="app-muted">пришли</span>
              </Panel>
              <Panel>
                <strong>{info.rewarded}</strong>
                <span className="app-muted">сыграли</span>
              </Panel>
              <Panel>
                <Balance kind="coins" value={info.earned} compact />
                <span className="app-muted">заработано</span>
              </Panel>
            </div>

            <h3 className="app-section">Ваши приглашённые</h3>
            {info.friends.length === 0 ? (
              <EmptyState icon="users" title="Пока никого" text="Отправьте ссылку в чат с друзьями или в группу." />
            ) : (
              <Panel padded={false}>
                {info.friends.map((f) => (
                  <button key={f.id} type="button" className="friend-row invite-row" onClick={() => openPlayer(f.id)}>
                    <Avatar id={f.id} name={f.name} photoUrl={f.photoUrl} size={40} />
                    <div className="friend-row__body">
                      <strong>{f.name}</strong>
                      <span className="app-muted">{new Date(f.joinedAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}</span>
                    </div>
                    {f.rewardedAt ? (
                      f.coins > 0 ? <Badge tone="green">+{f.coins}</Badge> : <Badge tone="muted">лимит дня</Badge>
                    ) : (
                      <Badge tone="muted">ждём первую партию</Badge>
                    )}
                  </button>
                ))}
              </Panel>
            )}
          </>
        )}
      </QueryView>
    </div>
  );
}
