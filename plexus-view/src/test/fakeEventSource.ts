import type { EventSourceLike, FlowEvent } from '../api';

/** A stand-in for the browser's EventSource that records instances and lets a test push frames. */
export class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  static reset(): void {
    FakeEventSource.instances = [];
  }
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  readyState = 0;
  closed = false;
  private listeners = new Map<string, ((ev: MessageEvent) => void)[]>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close(): void {
    this.closed = true;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }
  /** Deliver a frame the way the API sends it: `event: toolcall`. */
  emit(ev: FlowEvent | string, type = 'toolcall'): void {
    const msg = { data: typeof ev === 'string' ? ev : JSON.stringify(ev) } as MessageEvent;
    for (const fn of this.listeners.get(type) ?? []) fn(msg);
  }
  fail(): void {
    this.onerror?.(new Event('error'));
  }
  static get last(): FakeEventSource | undefined {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }
}
