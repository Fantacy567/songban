import type { Check, EvidenceRef } from './contracts';
import type { Snapshot } from './workspace';

const sameRef = (a: EvidenceRef | null, b: EvidenceRef | null) => a === null || b === null
  ? a === b : a.id === b.id && a.revision === b.revision;

/** A feedback-only check is not a progress pointer. Keep its receipt usable only
 * for the exact current evidence and the run revision returned by that write. */
export function currentCheckReceipt(check: Check | null | undefined, snapshot: Snapshot, stage: Check['stage'], rubric: string | undefined, readback: EvidenceRef | null): Check | null {
  if (!check) return null;
  const { run, artifact } = snapshot;
  return !check.stale && check.run_id === run.id && check.learner_id === run.learner_id
    && check.stage === stage && check.parent_revision === run.revision
    && check.lesson_version_id === run.progress.find(p => p.stage === stage)?.lesson_version_id
    && check.rubric_version_id === rubric
    && check.artifact_version_id === (stage === 'clarify' ? null : artifact?.current_version.id || null)
    && sameRef(check.requirements_ref, run.current_requirements_ref)
    && sameRef(check.self_check_ref, run.current_self_check_ref)
    && sameRef(check.reflection_ref, run.current_reflection_ref)
    && sameRef(check.transfer_attempt_ref, run.current_transfer_attempt_ref)
    && sameRef(check.readback_ref, readback) ? check : null;
}
