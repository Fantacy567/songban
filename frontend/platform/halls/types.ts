/** Server-authorized projections only. These views never grant access or create work. */
export type HallAction =
  | { type: 'start-course'; courseId: string }
  | { type: 'continue-learning'; runId: string }
  | { type: 'view-work'; artifactId: string }
  | { type: 'prepare-learning' }
  | { type: 'hackathon-intro' }
  | { type: 'begin-practice' }
  | { type: 'resume-practice'; teamId: string }
  | { type: 'hackathon-hall' }
  | { type: 'retry'; page: 'ai' | 'hackathon' };

export interface HallButton { label: string; action: HallAction; disabled?: boolean }
export interface HallCover { src: string; alt: string; label?: string }
export interface HallStage { id: string; title: string; description?: string; order?: number }
export interface HallCourse {
  id: string;
  /** The original publication state must come from the server projection. */
  state: 'published' | 'trial' | 'archived';
  title: string;
  goal: string;
  stage: HallStage;
  preparation?: string;
  experience?: string;
  steps?: readonly string[];
  cover?: HallCover;
  statusLabel?: string;
  action?: HallButton;
  unavailableReason?: string;
}
export interface HallResume {
  title: string;
  description: string;
  action: HallButton;
}
export interface LearningHallState {
  page: 'ai';
  status: 'loading' | 'ready' | 'error';
  courses: readonly HallCourse[];
  /** Only the current learner's authorized work may be projected here. */
  resume?: HallResume | null;
  notice?: string;
  error?: string;
}
export interface HallPractice {
  teamId: string;
  title: string;
  stageLabel: string;
}
export interface HackathonHallState {
  page: 'hackathon';
  status: 'loading' | 'ready' | 'error';
  practice?: HallPractice | null;
  /** This is capability information, not a new participation grant. */
  practiceEnabled?: boolean;
  preparationNotice?: string;
  error?: string;
}
export interface HackathonIntroState {
  page: 'hackathon-intro';
  practice?: HallPractice | null;
  practiceEnabled?: boolean;
  preparationNotice?: string;
}
export type HallViewState = LearningHallState | HackathonHallState | HackathonIntroState;
export type HallActionHandler = (action: HallAction) => boolean | void | Promise<boolean | void>;
export interface HallViewProps { state: HallViewState; onAction: HallActionHandler }
export interface HallMountOptions extends HallViewProps {
  /** Change this key on identity/scope boundaries to discard local transient state. */
  contextKey: string;
}
export interface HallMountHandle { update(options: HallMountOptions): void; unmount(): void }
