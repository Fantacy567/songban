// Copyright (c) 2026 2292576833. AI workbench contribution; joint project ownership: COPYRIGHT.md.
import { createRoot } from 'react-dom/client';
import { Companion } from './Companion';
import type { CompanionMountHandle, CompanionProps } from './types';
export { Companion } from './Companion';
export type * from './types';

let singleton: CompanionMountHandle | null = null;
/** Mount one persistent host for both halls and the portfolio. Identity changes
 * remount private state; learning context hides this platform conversation. */
export function mountCompanion(host: HTMLElement, initial: CompanionProps): CompanionMountHandle {
  singleton?.unmount();
  const root = createRoot(host);
  let active = true;
  function render(props: CompanionProps) { root.render(<Companion key={props.identityKey} {...props} />); }
  const handle: CompanionMountHandle = {
    update(props) { if (active) render(props); },
    unmount() { if (!active) return; active = false; root.unmount(); if (singleton === handle) singleton = null; },
  };
  singleton = handle; render(initial); return handle;
}
declare global { interface Window { SongbanCompanion: { mount: typeof mountCompanion } } }
if (typeof window !== 'undefined') window.SongbanCompanion = { mount: mountCompanion };
