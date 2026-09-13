import { Activity, ShieldAlert, ShieldCheck, Brain, Loader2, Info } from "lucide-react";
import type { MLAnalysis } from "../../lib/api";
import { hasMLAnalysis } from "../../lib/api";

export type MlAnalysisStatus =
  | "idle" // not yet requested
  | "loading" // request in flight
  | "unavailable" // 404 / reading has NULL ML columns
  | "error" // API failure (network, 5xx)
  | "unauthorized" // 401 / 403 — RBAC boundary hit
  | "success"; // analysis data present

interface MlAnalysisSectionProps {
  /** Request lifecycle status — controls loading / error / unavailable states. */
  status: MlAnalysisStatus;
  /** ML analysis payload from GET …/analysis (null unless status === "success"). */
  analysis: MLAnalysis | null;
  /** Short message for error / unavailable states (from the API or generic). */
  message?: string | null;
  /** "latest" = latest reading for the station; "reading" = a specific reading. */
  variant?: "latest" | "reading";
  /** Timestamp of the analysed reading (ISO string) for the success footer. */
  readingTimestamp?: string | null;
}

function formatPercent(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatScore(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

/**
 * Authority-only "AI Analysis" section (Phase 7).
 *
 * Data honesty (mirrors backend Phase 6 wording):
 * - anomaly status is an *anomalous condition* indicator, never confirmed pollution;
 * - water quality is the *predicted water-quality class*, never laboratory confirmation;
 * - when the backend has no ML result we render "Analysis unavailable" — never a
 *   fabricated "Normal"/"Safe" default;
 * - no model filenames or model internals are shown.
 */
export default function MlAnalysisSection({
  status,
  analysis,
  message = null,
  variant = "latest",
  readingTimestamp = null,
}: MlAnalysisSectionProps) {
  const hasAnalysis = status === "success" && hasMLAnalysis(analysis);

  if (status === "loading" || status === "idle") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-analysis">
        <SectionHeader variant={variant} />
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
          <span>Loading AI analysis…</span>
        </div>
      </div>
    );
  }

  if (status === "unauthorized") {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 shadow-sm" data-testid="ml-analysis">
        <SectionHeader variant={variant} />
        <div className="mt-4 flex items-start gap-3 text-sm text-amber-800">
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" />
          <p>
            <span className="font-semibold">AI analysis is restricted to authority accounts.</span>
            {message && !message.includes("restricted to authority") ? ` ${message}` : ""} No
            analysis data is shown without authorization.
          </p>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 shadow-sm" data-testid="ml-analysis">
        <SectionHeader variant={variant} />
        <div className="mt-4 flex items-start gap-3 text-sm text-red-800">
          <Info className="h-5 w-5 shrink-0 text-red-500 mt-0.5" />
          <p>{message || "Failed to load AI analysis. Please try again later."}</p>
        </div>
      </div>
    );
  }

  if (status === "unavailable" || !hasAnalysis) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-analysis">
        <SectionHeader variant={variant} />
        <div className="mt-4 flex items-start gap-3 text-sm text-slate-500">
          <Info className="h-5 w-5 shrink-0 text-slate-400 mt-0.5" />
          <p>
            <span className="font-semibold text-slate-600">Analysis unavailable</span>
            {message ? ` — ${message}` : null} — no ML result exists for this reading (readings
            ingested before ML integration have no analysis). No default classification is assumed.
          </p>
        </div>
      </div>
    );
  }

  // status === "success" with a complete ML analysis
  const anomalyLabel = analysis!.anomaly_label;
  const isAnomalous = anomalyLabel === 1;
  const qualityLabel = analysis!.water_quality_label ?? "";
  const isUnsafe = qualityLabel === "Unsafe";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-analysis">
      <SectionHeader variant={variant} />

      {/* Top-line statuses */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <StatusTile
          label="Anomaly Status"
          value={isAnomalous ? "Anomalous condition" : "Normal condition"}
          valueTestId="ml-anomaly-status"
          tileClass={isAnomalous ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"}
          icon={
            isAnomalous ? (
              <ShieldAlert className="h-5 w-5 text-red-500" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-emerald-500" />
            )
          }
          valueClass={isAnomalous ? "text-red-700" : "text-emerald-700"}
        />
        <StatusTile
          label="Current Water Quality"
          value={`${qualityLabel} (predicted)`}
          valueTestId="ml-water-quality"
          tileClass={isUnsafe ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"}
          icon={
            isUnsafe ? (
              <ShieldAlert className="h-5 w-5 text-red-500" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-emerald-500" />
            )
          }
          valueClass={isUnsafe ? "text-red-700" : "text-emerald-700"}
        />
      </div>

      {/* Metric grid */}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="ml-metrics">
        <MetricTile label="Anomaly Score" value={formatScore(analysis!.anomaly_score)} />
        <MetricTile label="Safe Probability" value={formatPercent(analysis!.safe_probability)} />
        <MetricTile label="Unsafe Probability" value={formatPercent(analysis!.unsafe_probability)} />
      </div>

      {/* Honesty footnote */}
      <div className="mt-4 flex items-start gap-3 rounded-xl bg-slate-50 border border-slate-100 p-3.5 text-xs text-slate-500">
        <Info className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
        <p>
          The anomaly status identifies unusual sensor patterns and the water-quality class is the
          model's predicted class on its benchmark dataset. These are model outputs, not laboratory
          confirmation of contamination or guaranteed water safety.
          {readingTimestamp && (
            <>
              {" "}
              Analysis of reading recorded <span className="font-semibold text-slate-600">{formatTimestamp(readingTimestamp)}</span>
              {analysis!.ml_processed_at && (
                <>
                  {" "}· processed <span className="font-semibold text-slate-600">{formatTimestamp(analysis!.ml_processed_at)}</span>
                </>
              )}
              .
            </>
          )}
        </p>
      </div>
    </div>
  );
}

function SectionHeader({ variant }: { variant: "latest" | "reading" }) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2">
        <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-600">
          <Brain className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900" data-testid="ml-section-title">
            AI Analysis
          </h3>
          <p className="text-[11px] text-slate-400 font-medium">
            {variant === "latest"
              ? "Machine-learning analysis of the latest reading"
              : "Machine-learning analysis for this reading"}
          </p>
        </div>
      </div>
      <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2.5 py-0.5">
        Authority only
      </span>
    </div>
  );
}

function StatusTile({
  label,
  value,
  valueTestId,
  tileClass,
  icon: Icon,
  valueClass,
}: {
  label: string;
  value: string;
  valueTestId: string;
  tileClass: string;
  icon: React.ReactNode;
  valueClass: string;
}) {
  return (
    <div className={`rounded-xl border p-4 ${tileClass}`}>
      <div className="flex items-center gap-2">
        {Icon}
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
      </div>
      <p className={`mt-1.5 text-lg font-extrabold ${valueClass}`} data-testid={valueTestId}>
        {value}
      </p>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4 text-slate-400" />
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
      </div>
      <p className="mt-1.5 text-xl font-extrabold text-slate-900 font-mono">{value}</p>
    </div>
  );
}
