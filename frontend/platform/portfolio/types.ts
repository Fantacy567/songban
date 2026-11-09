import type { ReactNode } from 'react';
/** Matches app/platform_v1/schemas.py. Authorization remains server-side. */
export type Assistance = 'none_reported' | 'assisted' | 'generated' | 'unknown';
export interface SourceRef { domain: 'learning' | 'competition' | 'external'; id: string; version: string }
export interface WorkOutput { kind: 'text' | 'external_link'; label: string; text: string | null; url: string | null }
export interface WorkSummary {
  id: string; learner_id: string; origin: SourceRef['domain']; title: string; summary: string; revision: number;
  source_ref: SourceRef; current_version: { id: string; number: number }; actual_outputs: WorkOutput[];
  cover_asset_id: string | null; contribution: string;
  provenance: { kind: 'learning_record' | 'guardian_statement_learner_confirmed' | 'self_reported'; ai_assistance: Assistance; source_label: string };
  visibility: 'private'; updated_at: string; available_actions: string[];
}
export interface WorkVersion { id: string; number: number; actual_outputs: WorkOutput[]; created_at: string }
export interface WorkDetail extends WorkSummary { versions: WorkVersion[] }
export interface WorkList { items: WorkSummary[]; next_cursor: null }
export interface SourcePreview { ref: string; label: string; text: string; outputs: WorkOutput[] }
export interface CompetitionSource { project_id: string; name: string; source_revision: number; available_refs: SourcePreview[] }
export interface CompetitionSources { items: CompetitionSource[] }
export interface CompetitionLink {
  id: string; learner_id: string; project_id: string; source_revision: number; revision: number;
  state: 'offered' | 'accepted' | 'declined' | 'revoked'; title: string; summary: string; contribution: string;
  selected_refs: string[]; sources: SourcePreview[]; source_label: string; created_at: string; updated_at: string;
}
export interface CompetitionLinks { items: CompetitionLink[] }
export interface ExternalWorkInput {
  request_id: string; title: string; summary: string; url: string; tool_name: string; contribution: string; ai_assistance: Assistance;
}
export interface ExternalWorkVersionInput extends ExternalWorkInput { expected_revision: number }
export interface CompetitionLinkInput {
  request_id: string; project_id: string; expected_source_revision: number; selected_refs: string[];
  contribution: string; title: string; summary: string;
}
export interface CompetitionDecisionInput { request_id: string; expected_revision: number; decision: 'accept' | 'decline' | 'revoke' }
export type PortfolioTransport = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
export interface PortfolioPageProps {
  transport: PortfolioTransport;
  learnerId: string;
  mode: 'learner' | 'manager';
  identityKey: string;
  onOpenLearning: (runId?: string, artifactId?: string) => void | boolean | Promise<void | boolean>;
  onOpenCompetition?: (projectId: string) => void | boolean | Promise<void | boolean>;
  onOpenStudio?: (projectId: string) => void | boolean | Promise<void | boolean>;
  onDirty?: (dirty: boolean) => void;
  onCurrentWork?: (work: WorkDetail | null) => void;
  /** Central-owned authorized image panel; rendered only for learner details. */
  renderImageTools?: (work: WorkDetail) => ReactNode;
  /** Refresh read-only projections after an authorized image/archive operation. */
  refreshToken?: number;
  /** Protect an unsaved image draft before changing the local work/editor view. */
  beforeTransition?: () => boolean | Promise<boolean>;
  /** Central must resolve an already authorized private asset to a same-origin URL. */
  getAssetUrl?: (assetId: string) => string | null;
}
