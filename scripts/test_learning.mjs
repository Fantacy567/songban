// Isolated browser fixtures only. Never opens production services or identities.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const evidence = resolve(process.env.SONGBAN_LEARNING_TEST_OUTPUT || resolve(root, '../outputs/learning-tests', new Date().toISOString().replaceAll(':', '-')));
const env = { ...process.env,
  SONGBAN_LEARNING_EVIDENCE: resolve(evidence, 'identity-start'),
  SONGBAN_P2_EVIDENCE: resolve(evidence, 'three-gates'),
  SONGBAN_LEARNING_REGRESSION_EVIDENCE: resolve(evidence, 'regressions'),
  SONGBAN_P3_REPORT_EVIDENCE: resolve(evidence, 'reports'),
  SONGBAN_STUDIO_EVIDENCE: resolve(evidence, 'studio'),
  SONGBAN_COMPANION_EVIDENCE: resolve(evidence, 'companion'),
  SONGBAN_ENTRY_EVIDENCE: resolve(evidence, 'entry-flow'),
  SONGBAN_COURSE_HALL_EVIDENCE: resolve(evidence, 'course-hall'),
  SONGBAN_ACCESSIBILITY_EVIDENCE: resolve(evidence, 'accessibility'),
};
for (const file of ['frontend/learning/tests/browser.cjs', 'frontend/learning/tests/p2-browser.cjs', 'frontend/learning/tests/p3-reports.cjs', 'frontend/learning/tests/regressions.cjs', 'frontend/learning/tests/studio.cjs', 'frontend/learning/tests/companion.cjs', 'frontend/learning/tests/entry-flow.cjs', 'frontend/learning/tests/course-hall.cjs', 'frontend/learning/tests/accessibility.cjs', 'tests/learning_host_navigation.cjs']) {
  const result = spawnSync(process.execPath, [file], { cwd: root, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
console.log(`Learning browser evidence: ${evidence}`);
