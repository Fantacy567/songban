export interface CompanionContext {
  domain: 'hall' | 'learning' | 'portfolio' | 'competition';
  resource_id?: string | null;
  learner_id?: string | null;
}
export type CompanionAction = {
  kind: 'open_course_hall' | 'open_hackathon_hall' | 'open_portfolio' | 'open_competition_team';
  label: string; resource_id: string | null;
};
export interface CompanionTurn {
  id: string; request_id: string; conversation_id: string; question: string; text: string | null;
  role_id: 'guide' | 'portfolio_guide' | 'competition_guide'; mode: 'static' | 'mock' | 'live';
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'unknown'; prompt_version: string; actual_model: string | null;
  visibility?: 'normal' | 'restricted';
  sources: { source_id: string; source_version: string; source_domain: string; nature: string }[];
  actions: CompanionAction[]; created_at: string; parent_revision: number;
}
export interface LearningAdapter { kind: 'learning_run'; run_id: string }
export interface CompanionConversation {
  id: string; revision: number; context: CompanionContext; adapter: LearningAdapter | null;
  capabilities: { static_available: boolean; mock_available: boolean; live_available: boolean; notice: string };
  messages: CompanionTurn[]; has_earlier: boolean;
}
export interface CompanionSend {
  request_id: string; expected_revision: number; question: string; mode: 'static' | 'mock' | 'live';
}
/** The host supplies authenticated same-origin transport, identity fences and CSRF.
 * It must never automatically replay a mutation or exchange cookie/Bearer roles. */
export interface CompanionTransport {
  open(body: { request_id: string; context: CompanionContext }): Promise<CompanionConversation>;
  read(conversationId: string): Promise<CompanionConversation>;
  send(conversationId: string, body: CompanionSend): Promise<CompanionTurn>;
  readMessage(conversationId: string, messageId: string): Promise<CompanionTurn>;
}
export interface CompanionProps {
  identityKey: string;
  context: CompanionContext;
  transport: CompanionTransport;
  presentation?: 'floating' | 'embedded';
  disabled?: boolean;
  onAction(action: CompanionAction): void | Promise<void>;
  /** The old course already renders CompanionPanel. This bridge must not mount
   * another platform dialog or copy course messages into platform history. */
  onLearningAdapter?(adapter: LearningAdapter): void;
  /** Host leave guards may protect unsent text and unresolved operations. */
  onDirty?(dirty: boolean): void;
}
export interface CompanionMountHandle { update(props: CompanionProps): void; unmount(): void }
