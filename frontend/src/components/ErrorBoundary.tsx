import { Component, type ReactNode } from "react";

/** Recover from unexpected rendering failures without exposing exception details. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } { return { failed: true }; }
  render(): ReactNode {
    if (this.state.failed) return <main className="panel" role="alert">
      <h1>CartPilot could not display this page</h1>
      <p>Reload the page to try again. Your stored data is retained.</p>
      <button onClick={() => window.location.reload()}>Reload page</button>
    </main>;
    return this.props.children;
  }
}
