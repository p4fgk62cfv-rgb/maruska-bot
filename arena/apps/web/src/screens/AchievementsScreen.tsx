import type { AchievementDto } from '@arena/shared';
import { Badge, Icon, Panel, ProgressBar } from '@arena/ui';
import { ACHIEVEMENT_ICON } from '../lib/achievements.js';
import { useQuery } from '../lib/useQuery.js';
import { QueryView, ScreenHeader } from './common.js';


export default function AchievementsScreen() {
  const query = useQuery<AchievementDto[]>('/achievements');
  const unlocked = query.data?.filter((a) => a.unlockedAt).length ?? 0;
  return (
    <div className="app-stack">
      <ScreenHeader title="Достижения" subtitle={query.data ? `${unlocked} из ${query.data.length}` : undefined} />
      <QueryView query={query}>
        {(list) => (
          <div className="app-list">
            {list.map((a) => (
              <Panel key={a.key} className={`ach${a.unlockedAt ? ' ach--done' : ''}`}>
                <span className="ach__icon">
                  <Icon name={ACHIEVEMENT_ICON[a.icon] ?? 'star'} />
                </span>
                <div className="ach__body">
                  <div className="app-row app-row--between">
                    <strong>{a.title}</strong>
                    {a.unlockedAt ? <Badge tone="gold">Получено</Badge> : <span className="app-muted">{a.progress}/{a.goal}</span>}
                  </div>
                  <span className="app-muted">{a.description}</span>
                  {!a.unlockedAt && a.goal > 1 && <ProgressBar value={a.progress} max={a.goal} tone="gold" />}
                </div>
              </Panel>
            ))}
          </div>
        )}
      </QueryView>
    </div>
  );
}
