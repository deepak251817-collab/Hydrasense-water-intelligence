import { useEffect, useState } from "react";
import { Brain, Loader2, Info, ShieldAlert, ShieldCheck } from "lucide-react";
import type { MonitoringStation, ReadingAnalysisResponse } from "../../lib/api";
import { authorityApi, hasMLAnalysis } from "../../lib/api";
import { getToken } from "../../lib/auth";
type FetchStatus = "loading" | "success" | "partial" | "error" | "unauthorized";

interface StationMLStatus {
  station: MonitoringStation;
  /** null = no readable ML analysis (no reading, pre-ML reading, or per-station failure) */
  anomalous: boolean | null;
  unsafe: boolean | null;
}

/**
 * Authority command-center ML summary (Phase 7, spec §7).
 *
 * Values are computed ONLY from backend per-station analysis endpoints —
 * no fabricated aggregates, and no new backend endpoint is created. Stations
 * whose analysis cannot be read (no reading yet, or a per-request failure)
 * are reported separately as "not analysed" rather than silently counted as
 * normal — a degraded fleet view is shown honestly.
 */
export default function MlSummaryCard({ stations }: { stations: MonitoringStation[] }) {
  const [results, setResults] = useState<StationMLStatus[] | null>(null);

  // Derived synchronous states (react-hooks/set-state-in-effect): guard states
  // are computed at render time; the effect only stores async results.
  const token = getToken();
  const status: FetchStatus =
    !token
      ? "unauthorized"
      : stations.length === 0
        ? "success"
        : results === null
          ? "loading"
          : results.some((r) => r.anomalous !== null || r.unsafe !== null)
            ? "success"
            : "partial";

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    if (stations.length === 0) return;

    let cancelled = false;

    const classify = (
      data: ReadingAnalysisResponse | null
    ): { anomalous: boolean; unsafe: boolean } | null => {
      if (!data || !data.ml || !hasMLAnalysis(data.ml)) return null;
      return {
        anomalous: data.ml.anomaly_label === 1,
        unsafe: data.ml.water_quality_label === "Unsafe",
      };
    };

    Promise.all(
      stations.map(async (station): Promise<StationMLStatus> => {
        try {
          const data = await authorityApi.getLatestStationAnalysis(station.station_code, token);
          if (cancelled) {
            return { station, anomalous: null, unsafe: null };
          }
          const flags = classify(data);
          return { station, anomalous: flags?.anomalous ?? null, unsafe: flags?.unsafe ?? null };
        } catch {
          // 404 (no readings) or a transient failure — counted as "not analysed".
          return { station, anomalous: null, unsafe: null };
        }
      })
    ).then((rows) => {
      if (cancelled) return;
      setResults(rows);
    });

    return () => {
      cancelled = true;
    };
  }, [stations]);

  if (status === "unauthorized") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-summary">
        <SummaryHeader />
        <div className="mt-4 flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-4">
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" />
          <p>AI analysis summary is restricted to authority accounts.</p>
        </div>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-summary">
        <SummaryHeader />
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
          <span>Analyzing stations…</span>
        </div>
      </div>
    );
  }

  const rows = results ?? [];

  const analysed = rows.filter((r) => r.anomalous !== null || r.unsafe !== null);
  const anomalousCount = rows.filter((r) => r.anomalous === true).length;
  const unsafeCount = rows.filter((r) => r.unsafe === true).length;
  const notAnalysed = rows.length - analysed.length;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ml-summary">
      <SummaryHeader />

      {rows.length === 0 ? (
        <div className="mt-4 flex items-start gap-3 text-sm text-slate-500">
          <Info className="h-5 w-5 shrink-0 text-slate-400 mt-0.5" />
          <p>No monitoring stations are available to analyze.</p>
        </div>
      ) : analysed.length === 0 ? (
        <div className="mt-4 flex items-start gap-3 text-sm text-slate-500">
          <Info className="h-5 w-5 shrink-0 text-slate-400 mt-0.5" />
          <p>
            ML analysis is not available for any station yet — readings ingested before ML
            integration have no analysis. Counts will appear as telemetry is processed.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div
              className={`rounded-xl border p-4 ${
                anomalousCount > 0 ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"
              }`}
            >
              <div className="flex items-center gap-2">
                {anomalousCount > 0 ? (
                  <ShieldAlert className="h-4.5 w-4.5 text-red-500" />
                ) : (
                  <ShieldCheck className="h-4.5 w-4.5 text-emerald-500" />
                )}
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Anomalous Stations
                </span>
              </div>
              <p
                className={`mt-1 text-2xl font-extrabold ${anomalousCount > 0 ? "text-red-700" : "text-emerald-700"}`}
                data-testid="ml-summary-anomalous"
              >
                {anomalousCount}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">of {analysed.length} analysed</p>
            </div>

            <div
              className={`rounded-xl border p-4 ${
                unsafeCount > 0 ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"
              }`}
            >
              <div className="flex items-center gap-2">
                {unsafeCount > 0 ? (
                  <ShieldAlert className="h-4.5 w-4.5 text-red-500" />
                ) : (
                  <ShieldCheck className="h-4.5 w-4.5 text-emerald-500" />
                )}
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Unsafe Predictions
                </span>
              </div>
              <p
                className={`mt-1 text-2xl font-extrabold ${unsafeCount > 0 ? "text-red-700" : "text-emerald-700"}`}
                data-testid="ml-summary-unsafe"
              >
                {unsafeCount}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">predicted class, of {analysed.length} analysed</p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
            <span>
              {rows.length} station{rows.length !== 1 ? "s" : ""} monitored
              {notAnalysed > 0 && (
                <span className="font-semibold text-amber-600"> · {notAnalysed} not analysed yet</span>
              )}
            </span>
            <span className="inline-flex items-center gap-1">
              <Info className="h-3.5 w-3.5" />
              Model outputs (predicted classes), not laboratory confirmation
            </span>
          </div>

          {notAnalysed > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {rows
                .filter((r) => r.anomalous === null && r.unsafe === null)
                .map((r) => (
                  <li
                    key={r.station.id}
                    className="rounded-full bg-slate-50 border border-slate-200 px-2.5 py-0.5 text-[10px] font-bold text-slate-500"
                  >
                    {r.station.station_code}
                  </li>
                ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function SummaryHeader() {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2">
        <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-600">
          <Brain className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900" data-testid="ml-summary-title">
            AI Analysis Summary
          </h3>
          <p className="text-[11px] text-slate-400 font-medium">
            Latest-reading machine-learning results across monitored stations
          </p>
        </div>
      </div>
      <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2.5 py-0.5">
        Authority only
      </span>
    </div>
  );
}
