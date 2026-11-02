import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  Flame,
  Loader2,
  Mail,
  RefreshCw,
  Send,
} from "lucide-react";
import { incidentsApi } from "../../lib/api";
import type {
  ApiError,
  IncidentDetail,
  IncidentListItem,
  LabContact,
  LabNotificationStatus,
} from "../../lib/api";
import { getToken } from "../../lib/auth";

const STATUS_STYLES: Record<string, string> = {
  raised: "bg-amber-50 text-amber-800 border-amber-200",
  lab_notified: "bg-cyan-50 text-cyan-800 border-cyan-200",
  sample_collected: "bg-indigo-50 text-indigo-800 border-indigo-200",
  result_received: "bg-blue-50 text-blue-800 border-blue-200",
  resolved: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

const PRIORITY_STYLES: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border-red-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-slate-50 text-slate-700 border-slate-200",
};

/**
 * Honest delivery badges. `smtp_unconfigured` and `failed` must never look
 * like a delivered report — the email may not have left the server.
 */
const DELIVERY_STYLES: Record<
  LabNotificationStatus,
  { label: string; className: string }
> = {
  not_notified: {
    label: "Lab not notified",
    className: "bg-slate-50 text-slate-600 border-slate-200",
  },
  sent: {
    label: "Report emailed",
    className: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  smtp_unconfigured: {
    label: "Email not configured",
    className: "bg-amber-50 text-amber-800 border-amber-200",
  },
  failed: {
    label: "Email failed",
    className: "bg-red-50 text-red-700 border-red-200",
  },
};

function deliveryFor(status: string) {
  return (
    DELIVERY_STYLES[status as LabNotificationStatus] ?? DELIVERY_STYLES.not_notified
  );
}

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

interface DeliveryOutcome {
  status: LabNotificationStatus;
  message: string;
}

export default function Incidents() {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [contacts, setContacts] = useState<LabContact[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [labContactId, setLabContactId] = useState<string>("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [notifyError, setNotifyError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<DeliveryOutcome | null>(null);
  const [downloading, setDownloading] = useState(false);

  const loadIncidents = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setError("Your session has expired. Sign in again to view incidents.");
      setLoading(false);
      setLoadingContacts(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rows = await incidentsApi.list(token);
      setIncidents(rows);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        setError("Your session has expired. Sign in again to view incidents.");
      } else if (apiError.statusCode === 403) {
        setError("Authority access is required to view incidents.");
      } else {
        setError(apiError.detail || "Unable to load incidents.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const loadContacts = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setLoadingContacts(false);
      return;
    }
    setLoadingContacts(true);
    try {
      const rows = await incidentsApi.listLabContacts(token);
      setContacts(rows);
      setLabContactId((current) => current || (rows[0]?.id.toString() ?? ""));
    } catch {
      // The notify form will show an explanatory empty state instead.
      setContacts([]);
    } finally {
      setLoadingContacts(false);
    }
  }, []);

  useEffect(() => {
    const initialId = window.setTimeout(() => {
      void loadIncidents();
      void loadContacts();
    }, 0);
    return () => window.clearTimeout(initialId);
  }, [loadIncidents, loadContacts]);

  // Reset the detail-scoped state when a different incident is picked. This
  // lives in the click handler (not the effect) so the effect only schedules
  // the request and never calls setState synchronously.
  const handleSelect = useCallback((incidentId: number) => {
    setSelectedId(incidentId);
    setDetail(null);
    setDetailError(null);
    setOutcome(null);
    setNotifyError(null);
    setNote("");
    setLoadingDetail(true);
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const record = await incidentsApi.get(selectedId, token);
        if (cancelled) return;
        setDetail(record);
      } catch (err) {
        if (cancelled) return;
        setDetailError((err as ApiError).detail || "Unable to load this incident.");
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleNotify = useCallback(async () => {
    const token = getToken();
    if (!token || !detail) return;
    if (!labContactId) {
      setNotifyError("Choose the laboratory that should receive the report.");
      return;
    }
    setSending(true);
    setNotifyError(null);
    setOutcome(null);
    try {
      const updated = await incidentsApi.notifyLab(
        detail.id,
        {
          lab_contact_id: Number(labContactId),
          note: note.trim() ? note.trim() : undefined,
        },
        token
      );
      setDetail(updated);
      const contact = contacts.find(
        (row) => row.id === Number(labContactId)
      );
      const addressed = contact
        ? `${contact.organization} <${contact.email}>`
        : "the selected laboratory";
      const delivery = updated.lab_notification_status as LabNotificationStatus;
      if (delivery === "sent") {
        setOutcome({
          status: "sent",
          message: `Report emailed to ${addressed} at ${formatDate(
            updated.lab_notified_at
          )}.`,
        });
      } else if (delivery === "smtp_unconfigured") {
        setOutcome({
          status: "smtp_unconfigured",
          message:
            `SMTP is not configured on this server, so NO email was sent to ${addressed}. ` +
            "Download the PDF below and deliver it to the laboratory manually.",
        });
      } else if (delivery === "failed") {
        setOutcome({
          status: "failed",
          message:
            `Email delivery to ${addressed} failed — the message did not leave the server. ` +
            "Retry, or download the PDF below and deliver it manually.",
        });
      } else {
        setOutcome({
          status: "not_notified",
          message: "The laboratory was recorded but no email was attempted.",
        });
      }
      // Refresh the queue badge without disturbing the open detail view.
      const rows = await incidentsApi.list(token);
      setIncidents(rows);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 409) {
        setNotifyError(
          apiError.detail ||
            "The incident has moved past the notification step, so the lab can no longer be notified."
        );
      } else {
        setNotifyError(apiError.detail || "Unable to notify the laboratory.");
      }
    } finally {
      setSending(false);
    }
  }, [detail, labContactId, note, contacts]);

  const handleDownload = useCallback(async () => {
    const token = getToken();
    if (!token || !detail) return;
    setDownloading(true);
    setNotifyError(null);
    try {
      const blob = await incidentsApi.downloadReport(detail.id, token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${detail.reference || `incident-${detail.id}`}-report.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setNotifyError((err as ApiError).detail || "Unable to download the report.");
    } finally {
      setDownloading(false);
    }
  }, [detail]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-orange-50 px-2.5 py-1 text-xs font-bold text-orange-800 border border-orange-200">
            <Flame className="h-3.5 w-3.5 text-orange-600" />
            <span>Incident workflow</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Water Quality Incidents
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Live records from the authority API. Notifying a laboratory emails it the generated
            PDF report when SMTP is configured; when it is not, the delivery state is shown
            honestly and the report must be delivered manually.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadIncidents()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-slate-800 shadow-xs transition-colors self-start disabled:opacity-60"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] items-start">
        {/* Incident queue */}
        <section aria-label="Incident queue" className="space-y-3">
          {loading && incidents.length === 0 ? (
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-6 text-xs text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              <span>Loading incidents…</span>
            </div>
          ) : !loading && incidents.length === 0 && !error ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-xs text-slate-500">
              No incidents are recorded yet. Raise one from an alert or the station view to
              start the workflow.
            </div>
          ) : (
            incidents.map((incident) => {
              const delivery = deliveryFor(incident.lab_notification_status);
              const isSelected = incident.id === selectedId;
              return (
                <button
                  key={incident.id}
                  type="button"
                  onClick={() => handleSelect(incident.id)}
                  aria-pressed={isSelected}
                  className={`w-full text-left rounded-2xl border bg-white p-4 shadow-xs transition-colors hover:border-slate-300 ${
                    isSelected ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <span className="font-mono text-xs font-bold text-slate-400">
                        {incident.reference || `INC-${incident.id}`}
                      </span>
                      <h3 className="text-sm font-bold text-slate-900 mt-0.5">
                        {incident.title}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {incident.station_code} — {incident.station_name}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1.5">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${PRIORITY_STYLES[incident.priority] ?? PRIORITY_STYLES.low}`}
                      >
                        {incident.priority}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${STATUS_STYLES[incident.status] ?? "bg-slate-50 text-slate-700 border-slate-200"}`}
                      >
                        {titleCase(incident.status)}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${delivery.className}`}
                      >
                        {delivery.label}
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-400 border-t border-slate-100 pt-2">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      {formatDate(incident.raised_at)}
                    </span>
                    {incident.is_demo && (
                      <span className="rounded-full border border-dashed border-slate-300 px-2 py-0.5 font-semibold text-slate-500">
                        demonstration origin
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </section>

        {/* Detail + notify form */}
        <section aria-label="Incident detail" className="space-y-4">
          {loadingDetail ? (
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-6 text-xs text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              <span>Loading incident…</span>
            </div>
          ) : detailError ? (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>{detailError}</p>
            </div>
          ) : !detail ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-xs text-slate-500">
              Select an incident to see its timeline and notify a laboratory.
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-5">
              <div className="border-b border-slate-100 pb-3">
                <span className="font-mono text-xs font-bold text-slate-400">
                  {detail.reference || `INC-${detail.id}`}
                </span>
                <h2 className="text-base font-bold text-slate-900">{detail.title}</h2>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">{detail.summary}</p>
                {detail.alert_reason && (
                  <p className="mt-1 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">Alert reason:</span>{" "}
                    {detail.alert_reason}
                  </p>
                )}
              </div>

              {/* Delivery state */}
              <div
                role="status"
                className={`rounded-xl border p-3 text-xs ${
                  detail.lab_notification_status === "sent"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                    : detail.lab_notification_status === "failed"
                      ? "border-red-200 bg-red-50 text-red-900"
                      : detail.lab_notification_status === "smtp_unconfigured"
                        ? "border-amber-200 bg-amber-50 text-amber-900"
                        : "border-slate-200 bg-slate-50 text-slate-700"
                }`}
              >
                <span className="font-bold">
                  {deliveryFor(detail.lab_notification_status).label}:
                </span>{" "}
                {detail.lab_contact
                  ? `${detail.lab_contact.organization} (${detail.lab_contact.email}). `
                  : "no laboratory selected yet. "}
                {detail.lab_notification_status === "sent" &&
                  `Sent ${formatDate(detail.lab_notified_at)}.`}
                {detail.lab_notification_status === "smtp_unconfigured" &&
                  "No email left the server because SMTP is not configured."}
                {detail.lab_notification_status === "failed" &&
                  "The last email attempt did not leave the server."}
                {detail.lab_notification_status === "not_notified" &&
                  "The report has not been emailed to any laboratory."}
              </div>

              {/* Notify form */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                  <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Notify laboratory by email</span>
                </div>

                {loadingContacts ? (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    <span>Loading laboratory contacts…</span>
                  </div>
                ) : contacts.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    No laboratory contacts are registered, so no report can be emailed. Add a
                    contact via <code className="font-mono">POST /api/authority/lab-contacts</code>{" "}
                    first.
                  </p>
                ) : (
                  <>
                    <div className="space-y-1">
                      <label
                        htmlFor="lab-contact"
                        className="block text-xs font-semibold text-slate-700"
                      >
                        Laboratory
                      </label>
                      <select
                        id="lab-contact"
                        value={labContactId}
                        onChange={(event) => setLabContactId(event.target.value)}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 focus:border-slate-400 focus:outline-none"
                      >
                        {contacts.map((contact) => (
                          <option key={contact.id} value={contact.id}>
                            {contact.organization} — {contact.email}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label
                        htmlFor="lab-note"
                        className="block text-xs font-semibold text-slate-700"
                      >
                        Note to the laboratory{" "}
                        <span className="font-normal text-slate-400">(optional)</span>
                      </label>
                      <textarea
                        id="lab-note"
                        rows={3}
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        maxLength={2000}
                        placeholder="e.g. Please confirm the turbidity index reading for this sample."
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none"
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void handleNotify()}
                        disabled={sending || detail.status === "resolved" || detail.status === "sample_collected" || detail.status === "result_received"}
                        className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-slate-800 shadow-xs transition-colors disabled:opacity-60"
                      >
                        {sending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        ) : (
                          <Send className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        <span>Email report to lab</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDownload()}
                        disabled={downloading}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-xs transition-colors disabled:opacity-60"
                      >
                        {downloading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        ) : (
                          <Download className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        <span>Download PDF</span>
                      </button>
                    </div>
                  </>
                )}

                {notifyError && (
                  <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-900">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    <p>{notifyError}</p>
                  </div>
                )}

                {outcome && (
                  <div
                    className={`flex items-start gap-2 rounded-xl border p-3 text-xs ${
                      outcome.status === "sent"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                        : outcome.status === "failed"
                          ? "border-red-200 bg-red-50 text-red-900"
                          : "border-amber-200 bg-amber-50 text-amber-900"
                    }`}
                  >
                    {outcome.status === "sent" ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    <p>{outcome.message}</p>
                  </div>
                )}
              </div>

              {/* Audit timeline */}
              <div className="border-t border-slate-100 pt-3 space-y-2">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
                  Workflow timeline
                </span>
                <ol className="space-y-1.5">
                  {detail.events.map((event) => (
                    <li key={event.id} className="text-xs text-slate-600">
                      <span className="font-semibold text-slate-800">
                        {event.from_status
                          ? `${titleCase(event.from_status)} → ${titleCase(event.to_status)}`
                          : titleCase(event.to_status)}
                      </span>{" "}
                      <span className="text-slate-400">· {formatDate(event.created_at)}</span>
                      {event.note && (
                        <p className="text-[11px] text-slate-500">{event.note}</p>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
