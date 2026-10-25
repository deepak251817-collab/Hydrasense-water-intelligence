import { useEffect, useState } from "react";
import {
  Brain,
  FileSpreadsheet,
  Info,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import type { MLStatusResponse } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";

type FetchStatus = "unauthorized" | "loading" | "success" | "error";

type FetchedResult =
  | { ok: true; data: MLStatusResponse }
  | { ok: false; message: string };

/**
 * Authority model-health card (Phase 7 / Phase 6 evaluation transparency).
 *
 * Renders ONLY what GET /authority/ml/status returns:
 * - per-model load state from the live inference service;
 * - the computed evaluation report (ml/reports/evaluation_report.json).
 *
 * When the report has not been generated the card says so and names the
 * generation command — it never invents metrics. When the API is unreachable
 * it shows an explicit error state instead of placeholder numbers.
 */
export default function ModelHealthCard() {
  const [result, setResult] = useState<FetchedResult | null>(null);

  // Derived synchronous states (react-hooks/set-state-in-effect): guard states
  // are computed at render time; the effect only stores async results.
  const token = getToken();
  const status: FetchStatus = !token
    ? "unauthorized"
    : result === null
      ? "loading"
      : result.ok
        ? "success"
        : "error";

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let cancelled = false;

    authorityApi
      .getMlStatus(token)
      .then((data) => {
        if (!cancelled) setResult({ ok: true, data });
      })
      .catch((err: { detail?: string; statusCode?: number }) => {
        if (cancelled) return;
        setResult({
          ok: false,
          message:
            err.detail || "Failed to load model health. Please try again later.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "unauthorized") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs" data-testid="ml-health">
        <Header />
        <div className="mt-4 flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-4">
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" />
          <p>Model health and evaluation metrics are restricted to authority accounts.</p>
        </div>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs" data-testid="ml-health">
        <Header />
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
          <span>Loading model health…</span>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs" data-testid="ml-health">
        <Header />
        <div
          className="mt-4 flex items-start gap-3 text-sm text-red-800 bg-red-50 border border-red-200 rounded-xl p-4"
          data-testid="ml-health-error"
        >
          <TriangleAlert className="h-5 w-5 shrink-0 text-red-500 mt-0.5" />
          <p>
            {!result || result.ok
              ? "Model health is unavailable right now."
              : result.message}
          </p>
        </div>
      </div>
    );
  }

  if (!result?.ok) {
    // Unreachable: loading/error/unauthorized are handled above. Guards the
    // narrowing so `data` is a typed MLStatusResponse for the section below.
    return null;
  }

  const data = result.data;
  const evaluation = data.evaluation_available ? data.evaluation : null;
  const rf = evaluation?.random_forest;
  const iforest = evaluation?.isolation_forest;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-5" data-testid="ml-health">
      <Header />

      {/* Per-model load state */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="ml-health-models">
        {data.models.map((model) => (
          <div key={model.key} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                {model.name}
              </span>
              {model.loaded ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                  <ShieldCheck className="h-3 w-3" /> Loaded
                </span>
              ) : model.artifact_present ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                  <TriangleAlert className="h-3 w-3" /> Not loaded
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 border border-red-200 px-2 py-0.5 text-[10px] font-bold text-red-700">
                  <ShieldAlert className="h-3 w-3" /> Missing artifact
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mt-1.5">{model.role}</p>
            <p className="text-[10px] text-slate-400 mt-1">
              {model.live_inference
                ? `Live inference · features: ${model.features.join(", ")}`
                : "Offline analysis only — not served by the live API"}
            </p>
          </div>
        ))}
      </div>

      {/* Evaluation report */}
      {evaluation ? (
        <div className="space-y-4" data-testid="ml-health-evaluation">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-cyan-600" />
              <h4 className="text-xs font-bold text-slate-900">Evaluation Report</h4>
            </div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              {data.report} · generated{" "}
              {evaluation.generated_at
                ? new Date(evaluation.generated_at).toLocaleString()
                : "unknown"}
            </span>
          </div>

          {/* Random Forest (held-out benchmark test split) */}
          {rf?.available && rf.metrics ? (
            <div className="rounded-xl border border-slate-100 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Random Forest — {rf.task}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <MetricTile label="Accuracy" value={pct(rf.metrics.accuracy)} />
                <MetricTile label="F1 (macro)" value={pct(rf.metrics.f1_macro)} />
                <MetricTile label="ROC-AUC (Unsafe)" value={pct(rf.metrics.roc_auc_unsafe)} />
                <MetricTile
                  label="Balanced Acc."
                  value={pct(rf.metrics.balanced_accuracy)}
                />
                <MetricTile
                  label="Test samples"
                  value={String(rf.metrics.n_samples ?? rf.dataset?.n_test_samples ?? "—")}
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-400">
                Held-out stratified test split of the benchmark dataset — not these live
                sensors. The Safe/Unsafe label follows the dataset&apos;s labeling rule and is
                not laboratory confirmation.
              </p>
            </div>
          ) : null}

          {/* Isolation Forest (unsupervised — descriptive only) */}
          {iforest?.available && iforest.summary ? (
            <div className="rounded-xl border border-slate-100 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Isolation Forest — {iforest.task}
              </p>
              <div className="mt-2 grid grid-cols-3 gap-3 sm:grid-cols-4">
                <MetricTile
                  label="Readings scored"
                  value={String(
                    iforest.dataset?.n_scored_readings ?? "—"
                  )}
                />
                <MetricTile
                  label="Anomalies flagged"
                  value={String(iforest.summary.anomalies_flagged ?? "—")}
                />
                <MetricTile
                  label="Anomaly rate"
                  value={pct(iforest.summary.anomaly_rate)}
                />
                <MetricTile
                  label="Score range"
                  value={
                    iforest.summary.score_min !== undefined &&
                    iforest.summary.score_max !== undefined
                      ? `${iforest.summary.score_min.toFixed(3)} … ${iforest.summary.score_max.toFixed(3)}`
                      : "—"
                  }
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-400">
                Unsupervised: no ground-truth contamination labels exist, so
                accuracy/precision/recall are intentionally not reported. An anomaly is an
                unusual sensor pattern, not confirmed pollution.
              </p>
            </div>
          ) : null}

          {/* Limitations */}
          {evaluation.limitations && evaluation.limitations.length > 0 ? (
            <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Limitations
              </p>
              <ul className="mt-2 space-y-1">
                {evaluation.limitations.map((line) => (
                  <li key={line} className="flex items-start gap-2 text-[11px] text-slate-500">
                    <Info className="h-3.5 w-3.5 shrink-0 text-slate-400 mt-0.5" />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : (
        <div
          className="flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-4"
          data-testid="ml-health-no-evaluation"
        >
          <TriangleAlert className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" />
          <div>
            <p className="font-semibold">Evaluation report has not been generated.</p>
            <p className="text-xs mt-1">
              Run <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">python ml/scripts/build_evaluation_report.py</code>{" "}
              to compute real metrics from the saved model artifacts. No metrics are shown
              until it has been executed.
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center gap-1.5 text-[11px] text-slate-400 border-t border-slate-100 pt-3">
        <Brain className="h-3.5 w-3.5" />
        <span>
          Model outputs are statistical estimates from the saved artifacts — not laboratory
          measurements or guaranteed safety judgments.
        </span>
      </div>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2">
        <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-600">
          <Brain className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900" data-testid="ml-health-title">
            Model Health &amp; Evaluation
          </h3>
          <p className="text-[11px] text-slate-400 font-medium">
            Live model availability and computed evaluation metrics
          </p>
        </div>
      </div>
      <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2.5 py-0.5">
        Authority only
      </span>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <p className="mt-0.5 text-sm font-extrabold text-slate-800">{value}</p>
    </div>
  );
}

/** Format a [0, 1] metric as a percentage; missing values render as an em dash. */
function pct(value: number | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}
