import { ShieldAlert, ShieldCheck, Info } from "lucide-react";

/**
 * Compact ML indicators for live/latest readings (Phase 7):
 * predicted water-quality class, anomaly status, and anomaly score.
 *
 * Honesty: values come only from the backend ML pipeline; NULL/unknown renders
 * as "—" (never a fabricated "Normal"/"Safe"). Terminology matches the backend:
 * "anomalous condition" / "normal condition" / "predicted water-quality class".
 */
export default function MlIndicator({
  anomalyLabel,
  anomalyScore,
  qualityLabel,
}: {
  anomalyLabel: number | null;
  anomalyScore: number | null;
  qualityLabel: string | null;
}) {
  const isAnomalous = anomalyLabel === 1;
  const anomalyKnown = anomalyLabel !== null;
  const isUnsafe = qualityLabel === "Unsafe";
  const qualityKnown = qualityLabel !== null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="ml-indicator">
      {/* Predicted water-quality class */}
      <div className="rounded-xl border p-4 bg-white border-slate-200">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
          Predicted Water Quality
        </p>
        <div className="mt-1.5 flex items-center gap-2">
          {qualityKnown &&
            (isUnsafe ? (
              <ShieldAlert className="h-4.5 w-4.5 text-red-500" />
            ) : (
              <ShieldCheck className="h-4.5 w-4.5 text-emerald-500" />
            ))}
          <span
            className={`text-base font-extrabold ${
              qualityKnown ? (isUnsafe ? "text-red-700" : "text-emerald-700") : "text-slate-400"
            }`}
            data-testid="ml-indicator-quality"
          >
            {qualityKnown ? `${qualityLabel} (predicted)` : "—"}
          </span>
        </div>
      </div>

      {/* Anomaly status */}
      <div className="rounded-xl border p-4 bg-white border-slate-200">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Anomaly Status</p>
        <div className="mt-1.5 flex items-center gap-2">
          {anomalyKnown &&
            (isAnomalous ? (
              <ShieldAlert className="h-4.5 w-4.5 text-red-500" />
            ) : (
              <ShieldCheck className="h-4.5 w-4.5 text-emerald-500" />
            ))}
          <span
            className={`text-base font-extrabold ${
              anomalyKnown ? (isAnomalous ? "text-red-700" : "text-emerald-700") : "text-slate-400"
            }`}
            data-testid="ml-indicator-anomaly"
          >
            {anomalyKnown ? (isAnomalous ? "Anomalous condition" : "Normal condition") : "—"}
          </span>
        </div>
      </div>

      {/* Anomaly score */}
      <div className="rounded-xl border p-4 bg-white border-slate-200">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Anomaly Score</p>
        <p
          className={`mt-1 text-base font-extrabold font-mono ${
            anomalyScore !== null ? "text-slate-900" : "text-slate-400"
          }`}
          data-testid="ml-indicator-score"
        >
          {anomalyScore !== null ? anomalyScore.toFixed(3) : "—"}
        </p>
      </div>

      <p className="col-span-full flex items-start gap-2 text-[11px] text-slate-400">
        <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
        Model outputs from the backend ML pipeline — an unusual-pattern indicator and a predicted
        class on the benchmark dataset, not laboratory confirmation of contamination or safety.
      </p>
    </div>
  );
}
