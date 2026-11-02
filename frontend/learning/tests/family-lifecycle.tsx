/** Synthetic component harness for effect cleanup/restart and late reads. */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { FamilyPage } from '../FamilyPage';
import type { LearningApi } from '../api';
import type { Config, ConsentText, Family } from '../types';

const family: Family = { id: 'synthetic-family', revision: 1, learners: [{ id: 'synthetic-child', revision: 1, family_id: 'synthetic-family', display_name: '虚构学习者', age_band: null, guardian_link: { id: 'synthetic-link', learner_id: 'synthetic-child', revision: 1, status: 'pending', declared_relationship: '父母', verification_method: null } }] };
let families: Family[] = [family];
const holds = new Map<string, { promise: Promise<void>; release: () => void }>();
const completed: string[] = [];
const api = {
  async request(path: string, method = 'GET') {
    if (path === '/families' && method === 'POST') { families = [{ ...family, learners: [] }]; return families[0]; }
    if (path === '/families') return { items: families, next_cursor: null };
    if (path.startsWith('/families/')) return families[0];
    if (path.endsWith('/consents')) return { learner_id: 'synthetic-child', relationship_status: 'pending', visibility: 'own_submissions', items: [], next_cursor: null };
    throw new Error('Unexpected fixture request');
  },
  async consentText(version: string): Promise<ConsentText> {
    await holds.get(version)?.promise;
    completed.push(version);
    return { consent_version: version, locale: 'zh-CN', title: `文本 ${version}`, text: `虚构内容 ${version}`, text_sha256: '0'.repeat(64), scope_purposes: [], approval_status: 'draft', approved_at: null, acceptance_enabled: false, notice: '仅生命周期测试' };
  },
} as unknown as LearningApi;
const root = createRoot(document.getElementById('host')!);
const setGuard = () => {};
const enter = async () => {};
const harness = {
  completed,
  hold(version: string) { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); holds.set(version, { promise, release }); },
  release(version: string) { holds.get(version)?.release(); },
  empty() { families = []; },
  render(version: string, strict = false) {
    const config: Config = { contract_version: '0.2.1', learning_enabled: true, live_enabled: false, publication_enabled: false, age_band_options: [], consent_version: version, notice: '仅生命周期测试' };
    const child = <FamilyPage api={api} config={config} setGuard={setGuard} enter={enter} />;
    root.render(strict ? <StrictMode>{child}</StrictMode> : child);
  },
};
Object.assign(window, { familyHarness: harness });
