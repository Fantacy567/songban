import { createRoot } from 'react-dom/client';
import { ProjectWorkbench } from './ProjectWorkbench';
import { WorkbenchApi } from './songban-adapter';
import type { MountOptions } from './types';
import './workbench.css';

const mounts = new WeakMap<HTMLElement, { unmount(): void }>();
export function mount(host: HTMLElement, options: MountOptions) {
  mounts.get(host)?.unmount();
  const api = new WorkbenchApi(options);
  const root = createRoot(host);
  let active = true;
  root.render(<ProjectWorkbench options={options} api={api} />);
  const handle = { unmount() {
    if (!active) return;
    active = false; api.dispose(); root.unmount(); mounts.delete(host);
  } };
  mounts.set(host, handle);
  return handle;
}
declare global { interface Window { SongbanWorkbench: { mount: typeof mount } } }
window.SongbanWorkbench = { mount };
