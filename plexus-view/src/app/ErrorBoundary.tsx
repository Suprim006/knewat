import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** When this changes (e.g. the route), a caught error is cleared and the children render again. */
  resetKey?: string;
}
interface State {
  error: Error | null;
  resetKey?: string;
}

/**
 * Catches render errors from a page (e.g. unexpected free-form API data) so the shell, the nav and the
 * tenant selector stay usable instead of the whole app going blank.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (props.resetKey !== state.resetKey) return { error: null, resetKey: props.resetKey };
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('View render error:', error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="page error-boundary" role="alert">
        <h2>Something went wrong</h2>
        <p>This page could not be drawn. The rest of the app still works.</p>
        <pre className="mono">{error.message}</pre>
        <button type="button" className="btn" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
