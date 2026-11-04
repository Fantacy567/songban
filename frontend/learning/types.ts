/** Consumer types for the frozen, proposed learning-v2 0.2.1 P1 subset. */
export type Route = '#/family' | '#/learn' | '#/learn/first' | '#/learn/courses' | `#/learn/course?id=${CourseId}` | '#/learn/start' | '#/learn/create' | `#/learn/create?${string}` | '#/learning-admin' | '#/hackathon' | '#/hackathon/intro' | '#/portfolio' | `#/learn/run?${string}` | '#/learn/works' | `#/learn/works?${string}`;
export const courseIds = ['ai-tools', 'imagination', 'first-project', 'plugins', 'models', 'api', 'model-powered-app'] as const;
export type CourseId = typeof courseIds[number];
export type CourseStep = 'understand' | 'try' | 'reflect';
export interface SeriesCourse {
  id: CourseId; version: string; title: string; status: 'trial'; order: number;
  chapter: { id: string; title: string; order: number };
  goal: string; preparation: string; duration: string; intro: string;
  cover: { src: string; alt: string };
  steps: { id: CourseStep; title: string; instruction: string; example: string; prompt: string }[];
  activity: { kind: string; title: string; instruction: string };
  sources: { title: string; url: string; supports: string }[];
  review: { technical: string; education: string; pilot: string };
}
export interface LearningCatalog { version: string; courses: SeriesCourse[] }
export type CourseActivity = Record<string, string | boolean | string[]>;
export interface CourseProgress {
  course_id: CourseId; course_version: string; learner_id: string; revision: number;
  answers: Record<CourseStep, string>; activity: CourseActivity; project_id: string | null;
  updated_at: string | null; status: 'not_started' | 'saved';
}
export interface CourseSave { request_id: string; expected_revision: number; answers: CourseProgress['answers']; activity: CourseActivity; project_id: string | null }
export interface CourseExperiment { kind: 'teaching-api'; request: { operation: 'greet'; name: string }; response: { message: string }; notice: string }
export interface MountOptions {
  initialRoute?: Route;
  onRouteChange?: (route: Route) => void;
  /** S00 must synchronously stop old polling, clear old private state and credentials. */
  onIdentityBoundary?: (reason: string) => void;
  onSessionChange?: (session: Session | null) => void;
  onUnmount?: () => void;
}
export interface MountHandle {
  navigate(route: Route): Promise<boolean>;
  canLeave(): Promise<boolean>;
  revalidate(): Promise<void>;
  unmount(): void;
}
export interface Session { id: string; revision: number; mode: 'manager' | 'learner' | 'staff'; actor_id: string; learner_id: string | null; mode_epoch: number; scopes: string[]; expires_at: string }
export interface Bootstrap { csrf_token: string; browser_revision: number }
export interface Config { contract_version: string; learning_enabled: boolean; live_enabled: boolean; publication_enabled: boolean; age_band_options: string[]; consent_version: string; notice: string; live_model_config_version?: string | null; mock_enabled?: boolean; reports_enabled?: boolean; reports_readable?: boolean; studio_enabled?: boolean; catalog_enabled?: boolean }
export type Relationship = 'pending' | 'verified' | 'rejected' | 'revoked';
export interface LearnerSelf { id: string; revision: number; display_name: string; age_band: string | null }
export interface Learner extends LearnerSelf { family_id: string; guardian_link: { id: string; revision: number; learner_id: string; status: Relationship; declared_relationship: string; verification_method: string | null } }
export interface Family { id: string; revision: number; learners: Learner[] }
export type Scope = 'learning' | 'live_model' | 'parent_summary' | 'report_publication';
export interface Consent { id: string; revision: number; learner_id: string; consent_version: string; scopes: Scope[]; status: 'active' | 'revoked'; recorded_at: string; text_sha256: string; effective_scopes: Scope[] }
export interface Consents { learner_id: string; relationship_status: Relationship; visibility: string; items: Consent[]; next_cursor: string | null }
export interface ConsentText { consent_version: string; locale: string; title: string; text: string; text_sha256: string; scope_purposes: { scope: Scope; purpose: string }[]; approval_status: 'draft' | 'approved_for_pilot' | 'withdrawn'; approved_at: string | null; acceptance_enabled: boolean; notice: string }
export type Choice = 'guided' | 'try_first' | 'challenge';
export type Topic = 'age_band' | 'experience' | 'interests' | 'help_preference' | 'mini_attempt_text' | 'chosen_start';
export type Answer = { state: 'unanswered' | 'skipped'; value: null } | { state: 'answered'; value: string | string[] } | { state: 'accepted_default'; value: Choice; recommendation_revision: number };
export interface Start { id: string; revision: number; learner_id: string; answers: Record<Topic, Answer>; completion_status: 'not_started' | 'draft' | 'completed' | 'completed_with_skips'; mini_attempt_status: 'not_attempted' | 'skipped' | 'answered'; recommendation: Choice; recommendation_basis: 'rules' | 'insufficient_evidence'; recommendation_revision: number; recommendation_rule_version: string; recommendation_source_fields: Topic[]; missing_fields: Topic[]; skipped_fields: Topic[]; effective_start: Choice; effective_start_source: 'learner_choice' | 'accepted_default' | 'conservative_fallback'; saved_at: string | null }
export interface SaveStart { request_id: string; expected_revision: number; answers: Partial<Record<Topic, Answer>> }
