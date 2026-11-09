/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md. */
import type { CourseId } from '../types';
export interface Teacher {
  course_id: CourseId; name: string; opening: string; suggestions: string[]; goal: string;
  sources: { title: string; url: string; supports?: string }[]; tools: string[];
}
export interface SessionSummary { id: string; course_id: CourseId; title: string; revision: number; updated_at: string }
export interface Message {
  id: string; user_text: string; assistant_text: string | null; mode: 'mock' | 'live';
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'unknown'; actual_model: string | null;
  artifact: { title: string; content: string } | null; created_at: string;
}
export interface ArtifactVersion { id: string; title: string; content: string; source_message_id: string | null; created_at: string }
export interface ExplorationRecord {
  id: string; session_id: string; course_id: CourseId; title: string; summary: string; next_step: string;
  status: 'draft' | 'confirmed'; method: 'evidence' | 'model'; source_message_ids: string[];
  artifact_version_id: string | null; updated_at: string;
}
export interface SessionView extends SessionSummary {
  teacher: Teacher; capabilities: { mock: boolean; live: boolean; reason: string | null };
  messages: Message[]; artifact_versions: ArtifactVersion[]; selected_artifact_id: string | null; record: ExplorationRecord | null;
  confirmed_record?: ExplorationRecord | null; record_versions?: ExplorationRecord[];
}
export const workbenchPath = '/learning-workbench';
export const workbenchChanged = () => window.dispatchEvent(new Event('songban-workbench-changed'));
