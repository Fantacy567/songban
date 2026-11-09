// Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
import type { LearningApi } from '../learning/api';

export interface StudioFile { path: string; content: string }
export interface StudioVersion { id: string; number: number; actor: 'child' | 'ai' | 'system'; explanation: string; created_at: string }
export interface StudioJob { id: string; state: 'queued' | 'running' | 'succeeded' | 'failed' | 'unknown'; failure_code: string | null }
export interface Runtime { available: boolean; reason: string }
export interface StudioProject {
  id: string; title: string; idea: string; learner_id: string | null; revision: number; current_version_id: string | null;
  files: StudioFile[]; versions: StudioVersion[];
  messages: { id: string; role: 'user' | 'assistant'; text: string; job_id: string | null; created_at: string }[];
  jobs: StudioJob[]; archive: { id: string; version_id: string } | null; runtime: Runtime;
}
export interface StudioList { items: StudioProject[]; runtime: Runtime }
export interface StudioPreview { html: string; csp: string; version_id: string }
export interface CreativeStudioProps {
  api: Pick<LearningApi, 'platform'>;
  identityKey: string;
  learnerId?: string | null;
  initialProjectId?: string | null;
  onProjectChange?: (id: string | null) => void;
  onDirty?: (dirty: boolean) => void;
  beforeTransition?: () => Promise<boolean>;
  onOpenPortfolio?: () => void;
}
