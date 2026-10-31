export type RoleId = 'materials' | 'direction' | 'next_step';
export interface MountOptions {
  token: string; identityKey: string; teamId: string | null;
  onNavigate(page: string, target?: { teamId: string | null; noteId?: string }): void; onPrepareDirection(fields: Record<string, string>): void;
  onShared(): void; onUnauthorized(): void;
}
export interface Session { id: string; title: string; team_id: string | null; created_at: string; updated_at: string }
export interface Source { id: string; name: string; scope?: 'personal' | 'team'; version?: number | string; nature?: string; truncated?: boolean; status?: string; warnings?: unknown[] }
export interface Action { type: string; label?: string; fields?: Record<string, string>; page?: string }
export interface Message {
  id: string; session_id: string; request_id: string; role: 'user' | 'assistant'; text: string;
  created_at: string; role_id: RoleId; actions: Action[]; sources: Source[];
  requested_model: string | null; actual_model: string | null; mode: 'live' | 'fixture';
  coverage?: { truncated_source_ids: string[]; history_limited: boolean; source_selection_only: boolean };
}
export interface RequestRecord {
  id: string; request_id: string; session_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'unknown';
  error: { code: string; message: string } | null; created_at: string; updated_at: string; message_id: string | null;
}
export interface Context {
  personal_session_count?: number;
  workflow?: { accepted_tasks: number; total_tasks: number; next_action: { title: string; reason: string; page: string } };
  roles: { id: RoleId; name: string; description: string }[];
  team: { id: string; name: string; is_captain: boolean; revision: number; plan_version: number } | null;
  direction: { goal: string; rules: string; rubric: string; non_goals: string; deadline: string } | null;
  my_tasks: { key?: string; task_key?: string; title?: string; name?: string; status?: string; deliverable?: string }[];
  sources: Source[]; model: { configured: boolean; requested_model: string | null };
}
export interface Conversation { session: Session; messages: Message[]; requests: RequestRecord[] }
export interface TurnResult { request: RequestRecord; message: Message | null }
export interface Team { id: string; name: string }
export interface ShareCommand { request_id: string; message_id: string; team_id: string; summary: string; selected: true }
export interface ShareReceipt { note_id: string; report_id: string; duplicate: boolean; analysis_triggered: false; notice: string }
export const allowedPages = new Set(['direction', 'materials', 'library', 'team', 'members', 'tools', 'delivery', 'review', 'tasks']);
export function sourceNature(value?: string) {
  return ({ sample: '样例', unverified: '待核实', self_report: '个人自述', self_reported: '个人自述', organizer_notice: '主办方通知（需核实）', official: '官方资料（需核实）', user_provided: '用户提供' } as Record<string, string>)[value || ''] || (value ? '待核实' : '');
}
export const roles: { id: RoleId; name: string; description: string; prompt: string }[] = [
  { id: 'materials', name: '理资料', description: '找重点，核对未知', prompt: '帮我整理选中的资料，列出重点、矛盾和还需要核对的事。' },
  { id: 'direction', name: '想方向', description: '想清目标与范围', prompt: '我想做一个项目，帮我一起想清楚要解决的问题和最小成果。' },
  { id: 'next_step', name: '排下一步', description: '拆出可以开始的事', prompt: '根据共同方向和我的任务，帮我安排下一步，并说明怎样检查成果。' },
];
