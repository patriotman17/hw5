import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type ApprovalRequest, type Cash, type EventsResponse, type Ticket } from "./api";
import { buildRunView } from "./agents";
import { EventFeed } from "./components/EventFeed";
import { Header } from "./components/Header";
import { EmptyState } from "./components/Primitives";
import { TicketDetail } from "./components/TicketDetail";
import { TicketList } from "./components/TicketList";

type Tone = "ok" | "warn" | "error";
interface Toast { id: number; message: string; tone: Tone }

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

export default function App() {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [ticketsError, setTicketsError] = useState<string | null>(null);
  const [cash, setCash] = useState<Cash | null>(null);
  const [cashError, setCashError] = useState<string | null>(null);
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [events, setEvents] = useState<{ ticketId: number; data: EventsResponse } | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [runningIds, setRunningIds] = useState<Set<number>>(new Set());
  const [resetting, setResetting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [operator, setOperatorState] = useState(() => localStorage.getItem("cc-approver") ?? "");
  const setOperator = (name: string) => { setOperatorState(name); localStorage.setItem("cc-approver", name); };
  const toastId = useRef(0);

  const toast = useCallback((message: string, tone: Tone = "ok") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const refreshBoard = useCallback(async () => {
    const [t, c, r] = await Promise.allSettled([api.tickets(), api.cash(), api.approvalRequests()]);
    if (t.status === "fulfilled") { setTickets(t.value); setTicketsError(null); } else setTicketsError(errMsg(t.reason));
    if (c.status === "fulfilled") { setCash(c.value); setCashError(null); } else setCashError(errMsg(c.reason));
    if (r.status === "fulfilled") setRequests(r.value);
  }, []);

  const refreshEvents = useCallback(async (ticketId: number) => {
    try {
      const data = await api.events({ ticket_id: ticketId, limit: 300 });
      setEvents({ ticketId, data });
      setEventsError(null);
    } catch (e) {
      setEventsError(errMsg(e));
    }
  }, []);

  // Initial load + pick the first ticket.
  useEffect(() => { refreshBoard(); }, [refreshBoard]);
  useEffect(() => {
    if (selectedId == null && tickets?.length) setSelectedId(tickets[0].id);
  }, [tickets, selectedId]);

  const selected = tickets?.find((t) => t.id === selectedId) ?? null;
  const selectedRunning = !!selected && (selected.running || runningIds.has(selected.id));
  const anyRunning = runningIds.size > 0 || !!tickets?.some((t) => t.running);

  // Events: fast polling while the selected ticket is running, slow otherwise.
  useEffect(() => {
    if (selectedId == null) return;
    refreshEvents(selectedId);
    const t = setInterval(() => refreshEvents(selectedId), selectedRunning ? 1200 : 6000);
    return () => clearInterval(t);
  }, [selectedId, selectedRunning, refreshEvents]);

  // Board (tickets, cash, approval requests): every 3 s while anything runs, else every 8 s.
  useEffect(() => {
    const t = setInterval(refreshBoard, anyRunning ? 3000 : 8000);
    return () => clearInterval(t);
  }, [anyRunning, refreshBoard]);

  const currentEvents = events && events.ticketId === selectedId ? events.data : null;
  const fullView = useMemo(
    () => buildRunView(currentEvents?.events ?? [], currentEvents?.agent_activity ?? []),
    [currentEvents],
  );
  // Only show a run the backend still counts (latest_run since the last reset) or one in progress;
  // runs from before a reset stay in the event history but not in the run panels.
  const view = useMemo(() => {
    const current = fullView.running || (selected?.latest_run?.run_id != null && selected.latest_run.run_id === fullView.runId);
    return current ? fullView : buildRunView([], []);
  }, [fullView, selected?.latest_run?.run_id]);

  const runTicket = async (id: number) => {
    setRunningIds((s) => new Set(s).add(id));
    setTimeout(() => refreshEvents(id), 400);
    try {
      const res = await api.runTicket(id);
      toast(`Ticket #${id}: run finished — status is now ${res.status}.`, res.status === "resolved" ? "ok" : "warn");
    } catch (e) {
      toast(`Ticket #${id}: ${errMsg(e)}`, "error");
    } finally {
      setRunningIds((s) => { const n = new Set(s); n.delete(id); return n; });
      await Promise.all([refreshBoard(), refreshEvents(id)]);
    }
  };

  const afterChange = async (message: string, tone: Tone) => {
    toast(message, tone);
    await Promise.all([refreshBoard(), selectedId != null ? refreshEvents(selectedId) : Promise.resolve()]);
  };

  const reset = async () => {
    setResetting(true);
    try {
      const r = await api.reset();
      toast(`Shop reset to original data. Checking is back to $${r.checking_balance.toLocaleString()}.`, "ok");
    } catch (e) {
      toast(errMsg(e), "error");
    } finally {
      setResetting(false);
      await Promise.all([refreshBoard(), selectedId != null ? refreshEvents(selectedId) : Promise.resolve()]);
    }
  };

  return (
    <div className="app">
      <div className="starfield" aria-hidden="true" />
      <Header operator={operator} onOperator={setOperator} cash={cash} cashError={cashError} onReset={reset} resetting={resetting} anyRunning={anyRunning} />

      <div className="layout">
        <TicketList tickets={tickets} error={ticketsError} selectedId={selectedId} runningIds={runningIds} onSelect={setSelectedId} />

        {selected ? (
          <TicketDetail
            key={selected.id}
            ticket={selected}
            operator={operator}
            view={view}
            running={selectedRunning}
            requests={requests.filter((r) => r.ticket_id == null || r.ticket_id === selected.id)}
            onRun={() => runTicket(selected.id)}
            onChanged={afterChange}
          />
        ) : (
          <main className="detail">
            <section className="panel"><EmptyState title={ticketsError ? "Backend unreachable" : "Select a ticket"} hint={ticketsError ?? undefined} /></section>
          </main>
        )}

        <EventFeed
          events={view.runId ? view.events : currentEvents?.events ?? []}
          live={selectedRunning}
          loading={selectedId != null && !currentEvents}
          error={eventsError}
        />
      </div>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast toast--${t.tone}`}>{t.message}</div>)}
      </div>
    </div>
  );
}
