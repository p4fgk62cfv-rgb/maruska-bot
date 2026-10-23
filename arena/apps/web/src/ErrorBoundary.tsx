import { Component, type ReactNode } from 'react';
import { reportError } from './lib/errorReport.js';

/**
 * A crash while drawing the screen: instead of a white or frozen page the player gets a way back,
 * and the owner gets the error in «Журнал».
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: unknown, info: { componentStack?: string | null }): void {
    reportError('render', error, { component: (info.componentStack ?? '').slice(0, 600) });
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="app-center app-crash">
        <p>😵 Что-то пошло не так. Партия на сервере продолжается — вернитесь к ней.</p>
        <button type="button" className="ui-btn ui-btn--primary ui-btn--md" onClick={() => location.reload()}>
          Перезагрузить
        </button>
      </div>
    );
  }
}
