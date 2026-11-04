import { createRoot } from 'react-dom/client';
import { HallView } from './Halls';
import type { HallMountHandle, HallMountOptions } from './types';
export { HallView, LearningHall, HackathonHall, HackathonIntro } from './Halls';
export type * from './types';

const mounted = new WeakMap<HTMLElement, HallMountHandle>();
/** Native shell bridge. Identity, API requests, routes and leave guards stay with the caller. */
export function mountHalls(host: HTMLElement, options: HallMountOptions): HallMountHandle {
  mounted.get(host)?.unmount();
  const root = createRoot(host);
  let active = true;
  function render(value: HallMountOptions) {
    root.render(<HallView key={value.contextKey + ':' + value.state.page} state={value.state} onAction={value.onAction} />);
  }
  const handle: HallMountHandle = {
    update(value) { if (active) render(value); },
    unmount() { if (!active) return; active = false; root.unmount(); mounted.delete(host); },
  };
  mounted.set(host, handle); render(options); return handle;
}
declare global { interface Window { SongbanHalls: { mount: typeof mountHalls } } }
if (typeof window !== 'undefined') window.SongbanHalls = { mount: mountHalls };
