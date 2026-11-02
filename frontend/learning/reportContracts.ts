/** Frozen 0.2.1 report types; keep central contracts as the single schema source. */
export type { Report, Observation, Publication, DisputeRecord, Case, CaseEvidence, ManualFinding } from './contracts';
export const reportStates: Record<string, string> = { draft: '请核对事实', pending_review: '已送报告复核', published: '已发布给家长', failed: '报告整理未完成', revoked: '报告已撤回' };
export const generationStates: Record<string, string> = { pending: '正在排队', running: '正在整理', succeeded: '已整理', failed: '整理失败，作品仍保留', unknown: '结果还在核对，请勿重复生成' };
export const natureLabels: Record<string, string> = { child_statement: '孩子自己的说明', system_record: '系统记录', ai_suggestion: 'AI 整理建议', human_review: '人工复核意见' };
