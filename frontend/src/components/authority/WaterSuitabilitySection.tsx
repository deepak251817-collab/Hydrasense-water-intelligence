import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  Droplets,
  FlaskConical,
  Info,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type {
  ApiError,
  RecommendationSet,
  StationSuitabilityResponse,
  SuitabilityParameterStatus,
  WaterSuitabilityAssessment,
} from "../../lib/api";
import { authorityApi, publicApi } from "../../lib/api";
import { getToken } from "../../lib/auth";

type Props = {
  stationCode: string | null;
  /** "authority" calls the authenticated endpoint; "public" the QR-page one. */
  mode?: "authority" | "public";
  className?: string;
};

type FetchState =
  | { kind: "idle" }
  | { kind: "ok"; data: StationSuitabilityResponse }
  | { kind: "unauthorized" }
  | { kind: "error"; message: string };

const RESULT_STYLES: Record<string, string> = {
  preliminary_suitable: "bg-emerald-50 border-emerald-200 text-emerald-800",
  treatment_required: "bg-amber-50 border-amber-200 text-amber-800",
  outside_limits: "bg-red-50 border-red-200 text-red-800",
  lab_confirmation_required: "bg-cyan-50 border-cyan-200 text-cyan-900",
  insufficient_data: "bg-slate-50 border-slate-200 text-slate-700",
};

const RESULT_DOT: Record<string, string> = {
  preliminary_suitable: "bg-emerald-500",
  treatment_required: "bg-amber-500",
  outside_limits: "bg-red-500",
  lab_confirmation_required: "bg-cyan-500",
  insufficient_data: "bg-slate-400",
};

const STATUS_STYLES: Record<SuitabilityParameterStatus, string> = {
  within_acceptable: "bg-emerald-100 text-emerald-700 border-emerald-200",
  within_permissible: "bg-amber-100 text-amber-700 border-amber-200",
  outside_limits: "bg-red-100 text-red-700 border-red-200",
  not_measured: "bg-slate-100 text-slate-500 border-slate-200",
  not_comparable: "bg-amber-50 text-amber-700 border-amber-200",
};

const EMPTY_ADVICE: RecommendationSet = {
  recommendations: [],
  missing_assessments: [],
  urgency: null,
  authority_actions: [],
};

const FRESHNESS_LABELS: Record<string, string> = {
  fresh: "Fresh data",
  delayed: "Delayed data",
  stale: "Stale data",
  no_data: "No data",
};

const FRESHNESS_STYLES: Record<string, string> = {
  fresh: "bg-emerald-100 text-emerald-700 border-emerald-200",
  delayed: "bg-amber-100 text-amber-700 border-amber-200",
  stale: "bg-red-100 text-red-700 border-red-200",
  no_data: "bg-slate-100 text-slate-500 border-slate-200",
};

/**
 * Water Suitability Assessment panel (BIS IS 10500 / CPCB DBU).
 *
 * Renders exactly what the backend assessed from the latest reading:
 * per-criterion outcomes, missing tests, freshness and provenance. It never
 * invents a value, never upgrades a provisional estimate to a measurement, and
 * never presents a rule-based screening as machine learning or as a
 * laboratory certificate.
 */
export default function WaterSuitabilitySection({
  stationCode,
  mode = "authority",
  className = "",
}: Props) {
  const [state, setState] = useState<FetchState>({ kind: "idle" });
  const [selectedUse, setSelectedUse] = useState<string | null>(null);

  // Derived guards (no synchronous setState in effects).
  const token = getToken();
  const status: "loading" | "ok" | "unauthorized" | "error" | "idle" =
    !stationCode
      ? "idle"
      : mode === "authority" && !token
        ? "unauthorized"
        : state.kind === "ok"
          ? "ok"
          : state.kind === "unauthorized"
            ? "unauthorized"
            : state.kind === "error"
              ? "error"
              : "loading";

  useEffect(() => {
    if (!stationCode) return;

    let cancelled = false;
    const load = async () => {
      try {
        if (mode === "authority") {
          const token = getToken();
          if (!token) {
            if (!cancelled) setState({ kind: "unauthorized" });
            return;
          }
          const data = await authorityApi.getStationSuitability(stationCode, token);
          if (!cancelled) setState({ kind: "ok", data });
        } else {
          const data = await publicApi.getSuitability(stationCode);
          if (!cancelled) setState({ kind: "ok", data });
        }
      } catch (err) {
        if (cancelled) return;
        const apiError = err as ApiError;
        if (apiError.statusCode === 401 || apiError.statusCode === 403) {
          setState({ kind: "unauthorized" });
        } else {
          setState({
            kind: "error",
            message: apiError.detail || "Suitability assessment is unavailable.",
          });
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [stationCode, mode]);

  const assessments = state.kind === "ok" ? state.data.assessments : [];

  // Cheap derivation (no memo): the selector only re-renders this panel.
  const active: WaterSuitabilityAssessment | null =
    assessments.length === 0
      ? null
      : (assessments.find((a) => a.use === selectedUse) ?? assessments[0]);

  if (status === "idle") {
    return (
      <div className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs ${className}`}>
        <Header />
        <p className="mt-4 text-sm text-slate-500">
          Select a monitoring station to view its water suitability assessment.
        </p>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div
        className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs ${className}`}
        data-testid="suitability-section"
      >
        <Header />
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
          <span>Assessing water suitability…</span>
        </div>
      </div>
    );
  }

  if (status === "unauthorized") {
    return (
      <div
        className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs ${className}`}
        data-testid="suitability-section"
      >
        <Header />
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
          <p>Suitability assessments are restricted to authority accounts.</p>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div
        className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs ${className}`}
        data-testid="suitability-section"
      >
        <Header />
        <div
          className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          data-testid="suitability-error"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
          <p>{state.kind === "error" ? state.message : "Suitability assessment is unavailable."}</p>
        </div>
      </div>
    );
  }

  if (!active) {
    return (
      <div
        className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs ${className}`}
        data-testid="suitability-section"
      >
        <Header />
        <p className="mt-4 text-sm text-slate-500">No suitability assessment is available yet.</p>
      </div>
    );
  }

  const quality = active.data_quality;
  const advice = active.recommendations ?? EMPTY_ADVICE;

  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4 ${className}`}
      data-testid="suitability-section"
    >
      <Header stationCode={stationCode} rulesetVersion={active.ruleset_version} />

      {/* Intended-use selector */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Intended water use">
        {assessments.map((item) => {
          const isActive = item.use === active.use;
          return (
            <button
              key={item.use}
              type="button"
              onClick={() => setSelectedUse(item.use)}
              aria-pressed={isActive}
              data-testid={`suitability-use-${item.use}`}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-bold transition ${
                isActive
                  ? "border-cyan-300 bg-cyan-50 text-cyan-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${RESULT_DOT[item.result]}`} />
              {item.use_label}
            </button>
          );
        })}
      </div>

      {/* Result banner */}
      <div
        className={`rounded-xl border p-4 ${RESULT_STYLES[active.result] ?? RESULT_STYLES.insufficient_data}`}
        data-testid="suitability-result"
        data-result={active.result}
      >
        <p className="text-[10px] font-bold uppercase tracking-wider opacity-70">
          {active.standard}
        </p>
        <p className="mt-1 text-sm font-extrabold">{active.result_label}</p>
        <p className="mt-1 text-xs leading-relaxed">{active.summary}</p>
      </div>

      {/* Data quality / provenance */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span
          className={`rounded-full border px-2 py-0.5 font-bold ${FRESHNESS_STYLES[quality.freshness]}`}
          data-testid="suitability-freshness"
        >
          {FRESHNESS_LABELS[quality.freshness] ?? quality.freshness}
        </span>
        {quality.reading_timestamp && (
          <span>Reading: {new Date(quality.reading_timestamp).toLocaleString()}</span>
        )}
        {quality.device_source && <span>Source: {quality.device_source}</span>}
        {quality.age_seconds !== null && quality.age_seconds !== undefined && (
          <span>Age: {formatAge(quality.age_seconds)}</span>
        )}
      </div>

      {/* Measured values */}
      {active.measured_values.length > 0 && (
        <div>
          <SectionLabel icon={<Droplets className="h-3.5 w-3.5" />} text="Measured values" />
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {active.measured_values.map((value) => (
              <div key={value.parameter} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {value.label}
                </p>
                <p className="mt-0.5 text-sm font-extrabold text-slate-800">
                  {formatNumber(value.value)}
                  {value.unit ? ` ${value.unit}` : ""}
                </p>
                <p className="text-[10px] text-slate-400">{value.source}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Criteria table */}
      <div>
        <SectionLabel icon={<ClipboardCheck className="h-3.5 w-3.5" />} text="Applicable criteria" />
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[11px]">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wider text-slate-400">
                <th className="py-1.5 pr-3 font-bold">Parameter</th>
                <th className="py-1.5 pr-3 font-bold">Measured</th>
                <th className="py-1.5 pr-3 font-bold">Reference criterion</th>
                <th className="py-1.5 font-bold">Status</th>
              </tr>
            </thead>
            <tbody>
              {active.parameters.map((parameter) => (
                <tr
                  key={parameter.parameter}
                  className="border-b border-slate-50 align-top"
                  data-testid={`suitability-parameter-${parameter.parameter}`}
                >
                  <td className="py-2 pr-3 font-semibold text-slate-700">{parameter.label}</td>
                  <td className="py-2 pr-3 text-slate-600">
                    {parameter.value === null
                      ? "—"
                      : `${formatNumber(parameter.value)}${parameter.unit ? ` ${parameter.unit}` : ""}`}
                  </td>
                  <td className="py-2 pr-3 text-slate-500">{parameter.reference}</td>
                  <td className="py-2">
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold ${STATUS_STYLES[parameter.status]}`}
                    >
                      {parameter.status_label}
                    </span>
                    {parameter.note && (
                      <p className="mt-1 text-[10px] text-slate-400">{parameter.note}</p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Missing tests */}
      {active.missing_parameters.length > 0 && (
        <div data-testid="suitability-missing">
          <SectionLabel
            icon={<FlaskConical className="h-3.5 w-3.5" />}
            text={`Required tests & measurements (${active.missing_parameters.length})`}
          />
          <ul className="mt-2 space-y-1.5">
            {active.missing_parameters.map((missing) => (
              <li key={missing.parameter} className="flex items-start gap-2 text-[11px] text-slate-600">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                <span>
                  <strong className="font-semibold text-slate-700">{missing.label}</strong> — {missing.why}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Rule-based recommendations (backend-derived; empty for a pass) */}
      {advice.recommendations.length > 0 && (
        <div data-testid="suitability-recommendations">
          <SectionLabel
            icon={<ShieldAlert className="h-3.5 w-3.5" />}
            text={`Recommended next steps${advice.urgency ? ` · ${advice.urgency} urgency` : ""}`}
          />
          <div className="mt-2 space-y-2">
            {advice.recommendations.map((item) => (
              <div
                key={`${item.parameter}-${item.direction}`}
                className="rounded-xl border border-slate-100 bg-white p-3"
                data-testid={`recommendation-${item.parameter}`}
              >
                <p className="text-xs font-bold text-slate-800">
                  {item.label}
                  {item.value !== null && (
                    <span className="font-semibold text-slate-500">
                      {" — "}
                      {formatNumber(item.value)}
                      {item.unit ? ` ${item.unit}` : ""}
                    </span>
                  )}
                </p>
                {item.reason && (
                  <p className="mt-0.5 text-[11px] text-slate-500">{item.reason}</p>
                )}
                {item.possible_causes.length > 0 && (
                  <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">
                    <span className="font-semibold text-slate-700">Possible causes: </span>
                    {item.possible_causes.join(" ")}
                  </p>
                )}
                <ul className="mt-1.5 space-y-1">
                  {item.actions.map((action) => (
                    <li key={action} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                      <Info className="mt-0.5 h-3 w-3 shrink-0 text-cyan-500" />
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
                {item.avoid.length > 0 && (
                  <p className="mt-1.5 text-[11px] text-amber-700">
                    <span className="font-semibold">Avoid: </span>
                    {item.avoid.join(" ")}
                  </p>
                )}
              </div>
            ))}
          </div>
          {advice.missing_assessments.length > 0 && (
            <ul className="mt-2 space-y-1">
              {advice.missing_assessments.map((missing) => (
                <li key={missing} className="flex items-start gap-2 text-[11px] text-slate-500">
                  <FlaskConical className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />
                  <span>{missing}</span>
                </li>
              ))}
            </ul>
          )}
          {advice.authority_actions.length > 0 && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3" data-testid="authority-actions">
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
                Incident workflow (authority)
              </p>
              <ol className="mt-1.5 space-y-1">
                {advice.authority_actions.map((step, index) => (
                  <li key={step} className="flex items-start gap-2 text-[11px] text-amber-900">
                    <span className="font-bold">{index + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      {/* Limitations */}
      {active.limitations.length > 0 && (
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          {active.limitations.map((limitation) => (
            <p key={limitation} className="text-[11px] leading-relaxed text-slate-500">
              {limitation}
            </p>
          ))}
        </div>
      )}

      <p className="flex items-start gap-1.5 border-t border-slate-100 pt-3 text-[11px] text-slate-400">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          Rule-based screening against documented standards — not a laboratory certificate and not
          an ML prediction. Uncalibrated or simulated values are excluded from every comparison.
        </span>
      </p>
    </div>
  );
}

function Header({
  stationCode,
  rulesetVersion,
}: {
  stationCode?: string | null;
  rulesetVersion?: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-600">
          <ShieldCheck className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900" data-testid="suitability-title">
            Water Suitability Assessment
          </h3>
          <p className="text-[11px] font-medium text-slate-400">
            BIS IS 10500 &amp; CPCB designated-best-use screening
            {stationCode ? ` · ${stationCode}` : ""}
          </p>
        </div>
      </div>
      <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-700">
        Ruleset {rulesetVersion ?? "—"}
      </span>
    </div>
  );
}

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
      {icon}
      {text}
    </p>
  );
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}
