// Typed client for the Campus Customs FastAPI backend (Problem 7).
// The backend is the source of truth for ticket status; nothing here infers it.

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export type TicketStatus = "open" | "pending" | "resolved";

export interface PendingPayment {
  kind: "rent" | "invoice";
  ref_id: number;
  payee: string | null;
  amount: number | null;
  state: "awaiting_approval" | "approved" | "declined" | "refused";
  decided_by: string | null;
}

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  notes: string | null;
  created_at: string;
  db_status: string;
  status: TicketStatus;
  status_reason: string;
  pending_payments: PendingPayment[];
  outstanding_actions: string[];
  signed_off_actions: { action: string; signed_off_by: string; note: string; at: string }[];
  waiting_actions: { action: string; waiting_on: string }[];
  running: boolean;
  desk_date: string;
  latest_run: { run_id: string; completed_at: string; recommendation: string | null } | null;
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  desk_date: string;
  open_invoice_total: number;
  upcoming_rent: { id: number; landlord: string; monthly_rent: number; next_due: string; days_until_due: number }[];
}

export interface Fact { statement: string; source: string }
export interface Draft { audience: string; recipient: string; subject: string; body: string; status: "draft"; sent: false }
export interface ProposedAction {
  description: string;
  kind: string;
  owner: string;
  vendor_id: number | null;
  blocked_by: string | null;
  requires_human_approval: boolean;
  satisfied_by_payment_approval?: boolean;
  conditional_on?: string | null;
}
export interface PaymentRequestProposal {
  kind: "rent" | "invoice";
  ref_id: number;
  payee: string;
  amount: number;
  reason: string;
}
export interface Decision {
  ticket_id: number;
  desk_date: string;
  recommendation: string;
  rationale: string;
  agents_consulted: AgentName[];
  facts: Fact[];
  proposed_actions: ProposedAction[];
  drafts: Draft[];
  payment_requests: PaymentRequestProposal[];
  rule_checks: { rule: string; status: "pass" | "blocked" | "not_applicable"; note: string }[];
  missing_data: string[];
}

export interface AuditEvent {
  seq: number;
  timestamp: string;
  run_id: string;
  ticket_id: number;
  agent: AgentName | null;
  event: string;
  tool?: string;
  args?: Record<string, unknown>;
  to_agent?: AgentName;
  task?: string;
  depth?: number;
  summary?: string;
  tools_called?: string[];
  delegated_to?: string[];
  reason?: string;
  error?: string;
  usage?: { total_tokens: number; requests: number; tool_calls: number };
  recommendation?: string;
  decision?: Decision;
  kind?: string;
  ref_id?: number;
  approved_by?: string;
}

export interface AgentActivity {
  run_id: string;
  ticket_id: number;
  agent: AgentName;
  requested_by: AgentName | null;
  status: "completed" | "running" | "failed" | "blocked";
  task?: string;
  said: string | null;
  recommendations?: string[];
  tools_used: string[];
  delegated_to: string[];
}

export interface EventsResponse {
  latest_seq: number;
  count: number;
  events: AuditEvent[];
  agent_activity: AgentActivity[];
}

export interface ApprovalRequest {
  id: string;
  kind: "rent" | "invoice";
  ref_id: number;
  account: string;
  payee: string;
  amount: number;
  description: string | null;
  due_date: string | null;
  cash_before: number;
  cash_after: number;
  ticket_id: number | null;
  run_id: string | null;
  requested_by: string;
  created_at: string;
  expires_at: string;
  status: "pending" | "approved" | "refused" | "declined" | "expired" | "cancelled_by_reset";
  decided_by: string | null;
  refusal_reason: string | null;
}

export interface RunResponse {
  run_id: string;
  ticket_id: number;
  decision: Decision;
  usage: { total_tokens: number; requests: number; tool_calls: number };
  agents_run: AgentName[];
  delegations_used: number;
  status: TicketStatus;
  status_reason: string;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join("; ");
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return fallback;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(data?.detail, `${res.status} ${res.statusText}`));
  return data as T;
}

export const api = {
  tickets: () => request<{ tickets: Ticket[] }>("GET", "/api/tickets").then((r) => r.tickets),
  ticket: (id: number) => request<Ticket>("GET", `/api/tickets/${id}`),
  runTicket: (id: number) => request<RunResponse>("POST", `/api/tickets/${id}/run`),
  events: (params: { ticket_id?: number; run_id?: string; limit?: number }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
    return request<EventsResponse>("GET", `/api/events?${q}`);
  },
  cash: () => request<Cash>("GET", "/api/cash"),
  approvalRequests: () =>
    request<{ requests: ApprovalRequest[] }>("GET", "/api/payments/requests").then((r) => r.requests),
  createApproval: (body: { kind: string; ref_id: number; ticket_id?: number; run_id?: string }) =>
    request<ApprovalRequest>("POST", "/api/payments/requests", body),
  approve: (id: string, approved_by: string) =>
    request<{ request: ApprovalRequest; cash: { balance_before: number; balance_after: number } }>(
      "POST", `/api/payments/requests/${id}/approve`, { approved_by, confirm: "APPROVE" },
    ),
  decline: (id: string, declined_by: string) =>
    request<{ request: ApprovalRequest }>("POST", `/api/payments/requests/${id}/decline`, { declined_by }),
  signOff: (ticketId: number, body: { run_id: string; action: string; signed_off_by: string; note: string }) =>
    request<Ticket>("POST", `/api/tickets/${ticketId}/signoffs`, { ...body, confirm: "SIGN OFF" }),
  reset: () => request<{ ok: boolean; checking_balance: number }>("POST", "/api/reset"),
};

const AGENT_NAMES = new Set(["boss", "inventory", "accounting", "facilities", "customer_service", "agent", "ai", "system"]);
/** Same rule the backend enforces: a real human name, never an agent name. */
export const isHumanName = (name: string) => name.trim().length > 1 && !AGENT_NAMES.has(name.trim().toLowerCase());

export const money = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });
