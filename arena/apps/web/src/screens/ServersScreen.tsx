import type { ServerDto } from '@arena/shared';
import { Badge, Icon, Panel } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { QueryView, ScreenHeader } from './common.js';

export default function ServersScreen() {
  const query = useQuery<ServerDto[]>('/servers');
  return (
    <div className="app-stack">
      <ScreenHeader title="Серверы" subtitle="Бонус рейтинга за победы" />
      <QueryView query={query}>
        {(servers) => (
          <div className="app-list">
            {servers.map((s) => (
              <Panel key={s.key} className="server-row">
                <span className="server-row__gem" style={{ color: s.color, boxShadow: `0 0 18px ${s.color}55` }}>
                  <Icon name="gem" />
                </span>
                <div className="server-row__body">
                  <strong>{s.name}</strong>
                  <span className="app-muted">{s.online} онлайн</span>
                </div>
                <Badge tone="gold">+{s.ratingBonus}%</Badge>
              </Panel>
            ))}
          </div>
        )}
      </QueryView>
    </div>
  );
}
