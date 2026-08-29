/** Stage 6 wire contracts mirrored from packages/agent/contracts.py. */

export const SCHEMA_VERSION = "1.0.0" as const;

export type ActionType =
  | "navigate"
  | "click"
  | "type"
  | "select"
  | "check"
  | "uncheck"
  | "press"
  | "scroll"
  | "wait"
  | "back"
  | "ask_user"
  | "handoff"
  | "stop";

export type VerificationStatus =
  | "UNVERIFIED"
  | "VERIFIED"
  | "FAILED"
  | "INCONCLUSIVE"
  | "UNCERTAIN"
  | "STALE";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type TerminalReason = "COMPLETED" | "USER_STOP" | "MAX_STEPS" | "SAFETY_STOP" | "ERROR";

export type ErrorCode =
  | "NONE"
  | "INVALID_ACTION"
  | "TARGET_NOT_FOUND"
  | "AMBIGUOUS_TARGET"
  | "STALE_OBSERVATION"
  | "TARGET_DISABLED"
  | "TARGET_NOT_VISIBLE"
  | "TARGET_NOT_EDITABLE"
  | "ACTION_TIMEOUT"
  | "NAVIGATION_INTERRUPTED"
  | "POLICY_BLOCKED"
  | "UNSUPPORTED_ACTION"
  | "EXECUTION_FAILED"
  | "VERIFICATION_FAILED"
  | "APPROVAL_REQUIRED"
  | "USER_TAKEOVER"
  | "MAX_STEPS_REACHED"
  | "INTERNAL_ERROR";

export interface UserCommand {
  schema_version: typeof SCHEMA_VERSION;
  command_id: string;
  session_id: string;
  text: string;
  modality: "text" | "voice_transcript";
  received_at: string;
}

export interface GoalSpec {
  schema_version: typeof SCHEMA_VERSION;
  task_id: string;
  objective: string;
  constraints: string[];
  allowed_actions: ActionType[];
  max_steps: number;
  risk_level: RiskLevel;
}

export interface AXNode {
  node_id: string;
  role: string;
  name: string;
  description: string | null;
  value_summary: string | null;
  states: Record<string, string | boolean | number>;
  level: number | null;
  disabled: boolean;
  focused: boolean;
  selected: boolean | null;
  checked: boolean | string | null;
  expanded: boolean | null;
  children: string[];
}

export interface Observation {
  schema_version: typeof SCHEMA_VERSION;
  observation_ref: string;
  version: number;
  url: string;
  title: string;
  captured_at: string;
  nodes: AXNode[];
  focused_node_id: string | null;
  content_hash: string;
  source: string;
  raw_char_count: number;
  compact_char_count: number;
  estimated_tokens: number;
  capture_latency_ms: number;
}

export interface AgentAction {
  schema_version: typeof SCHEMA_VERSION;
  step_id: string;
  action_type: ActionType;
  target_ref: string | null;
  input_value: string | null;
  key: string | null;
  observation_version: number;
  expected_effect: string;
  risk_level: RiskLevel;
  requires_approval: boolean;
}

export interface VerificationResult {
  schema_version: typeof SCHEMA_VERSION;
  verification_id: string;
  step_id: string;
  status: VerificationStatus;
  evidence: string[];
  before_observation_ref: string;
  after_observation_ref: string | null;
  checked_at: string;
  error_code: ErrorCode;
}

export interface RelevantItem {
  semantic_ref: string;
  label: string;
  reason: string;
  observation_version: number;
}

export interface TaskMapSnapshot {
  schema_version: typeof SCHEMA_VERSION;
  snapshot_id: string;
  session_id: string;
  run_id: string;
  version: number;
  observation_version: number;
  completed_items: string[];
  pending_items: string[];
  relevant_items: RelevantItem[];
  created_at: string;
}

export interface FocusHandoff {
  schema_version: typeof SCHEMA_VERSION;
  handoff_id: string;
  run_id: string;
  status: "NONE" | "REQUESTED" | "ACTIVE" | "RESUMING" | "COMPLETED";
  target_ref: string | null;
  announcement: string;
  created_at: string;
}

export interface AgentState {
  schema_version: typeof SCHEMA_VERSION;
  session_id: string;
  thread_id: string;
  run_id: string;
  task_id: string;
  goal: GoalSpec;
  constraints: string[];
  observation_version: number;
  task_map_version: number;
  active_semantic_ref: string | null;
  verification: VerificationResult | null;
  handoff_status: "NONE" | "REQUESTED" | "ACTIVE" | "RESUMING" | "COMPLETED";
  step_count: number;
  recovery_count: number;
  intervention_count: number;
  pending_interrupt: Record<string, unknown> | null;
  terminal_reason: TerminalReason | null;
  error_code: ErrorCode;
}

export interface RunResult {
  schema_version: typeof SCHEMA_VERSION;
  run_id: string;
  success: boolean;
  terminal_reason: TerminalReason;
  error_code: ErrorCode;
  step_count: number;
  recovery_count: number;
  intervention_count: number;
  duration_ms: number;
}

export type DisplayStatus = "VERIFIED_COMPLETED" | "PLANNED" | "UNCERTAIN" | "RELEVANT";

export interface TaskMapItem {
  item_id: string;
  label: string;
  status: DisplayStatus;
  semantic_ref: string | null;
  observation_version: number;
  verification_id: string | null;
  evidence: string[];
  reason: string | null;
}

export interface MapControlState {
  paused: boolean;
  takeover_active: boolean;
  approval_pending: boolean;
  handoff_status: "NONE" | "REQUESTED" | "ACTIVE" | "RESUMING" | "COMPLETED";
}

export interface AccessibleTaskMap {
  schema_version: "1.0.0";
  map_id: string;
  session_id: string;
  run_id: string;
  version: number;
  observation_version: number;
  goal: string;
  progress_label: string;
  verified_completed: TaskMapItem[];
  relevant_options: TaskMapItem[];
  next_action: TaskMapItem | null;
  uncertain_items: TaskMapItem[];
  control_state: MapControlState;
  final_summary: string | null;
  stale_invalidated_count: number;
  generated_at: string;
}

export type LiveRunStatus = "QUEUED" | "RUNNING" | "WAITING_USER" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface LiveRunResponse {
  run_id: string;
  benchmark_session_id: string;
  task_id: string;
  status: LiveRunStatus;
  announcement: string;
  task_map: AccessibleTaskMap | null;
  error: string | null;
}

export interface ActiveBenchmarkTask {
  session_id: string;
  task_id: string;
  goal?: string;
  study_session_id?: string;
  instruction?: string;
  task_index?: number;
  task_count?: number;
}
