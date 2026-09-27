import { EmptyState } from '@arena/ui';
import { ScreenHeader } from './common.js';

export default function SoonScreen({ title, text }: { title: string; text: string }) {
  return (
    <div className="app-stack">
      <ScreenHeader title={title} />
      <EmptyState icon="clock" title="Скоро" text={text} />
    </div>
  );
}
