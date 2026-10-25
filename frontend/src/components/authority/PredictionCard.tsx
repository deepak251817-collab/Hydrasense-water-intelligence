import { useEffect, useState } from "react";
import type { WaterSource } from "../../data/mockData";
import type { ForecastParameter, ForecastResponse } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Database,
  LineChart,
} from "lucide-react";

interface PredictionCardProps {
  selectedSource: WaterSource;
}

/** Primary monitoring station for each demonstration river. */
const STATION_BY_SOURCE: Record<string, string> = {
  "Arkavathi River": "ARK-001",
  "Cauvery River": "CAU-001",
  "Vrishabhavathi River": "VRS-001",
};

const HORIZON_CHOICES = [6, 12, 24, 48];

function fmt(value: number, parameter: string): string {
  if (parameter === "tds") return value.toFixed(0);
  if (parameter === "turbidity") return value.toFixed(1);
  return value.toFixed(2);
}

/** 3 significant digits so "0.047 vs 0.047" doesn't read as a tie. */
function fmtMetric(value: number): string {
  return String(Number(value.toPrecision(3)));
}

function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const diff = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(diff)) return "—";
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** Format a FUTURE forecast target time as an offset from now. */
function inLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const diff = new Date(value).getTime() - Date.now();
  if (!Number.isFinite(diff) || diff <= 0) return "at target";
  const hours = diff / 3600000;
  if (hours < 1) return `in ~${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `in ~${Math.round(hours)} h`;
  return `in ~${Math.round(hours / 24)} d`;
}

function ParameterRow({ param }: { param: ForecastParameter }) {
  if (param.status !== "ready" || param.points.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-slate-300">{param.label}</span>
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-extrabold uppercase text-amber-400">
            Not published
          </span>
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
          {param.message}
        </p>
        {param.model && (
          <p className="mt-1 text-[10px] text-slate-500">
            Holdout MAE {fmtMetric(param.model.mae)} vs persistence{" "}
            {fmtMetric(param.model.baseline_mae)} — evaluation did not support
            the model.
          </p>
        )}
      </div>
    );
  }

  const last = param.points[param.points.length - 1];
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-slate-300">{param.label}</span>
        <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-extrabold uppercase text-cyan-400">
          Forecast
        </span>
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="text-lg font-black tabular-nums text-white">
          {fmt(last.value, param.parameter)}
        </span>
        <span className="text-[10px] font-semibold text-slate-500">
          {param.unit}
        </span>
        <span className="ml-auto text-[10px] text-slate-500">
          now:{" "}
          {param.last_observed !== null
            ? fmt(param.last_observed, param.parameter)
            : "—"}
        </span>
      </div>
      <p className="mt-1 text-[10px] text-slate-500">
        {inLabel(last.timestamp)} · band{" "}
        {fmt(last.lower, param.parameter)}–{fmt(last.upper, param.parameter)}{" "}
        (±MAE)
      </p>
      {param.model && (
        <p className="mt-1 text-[10px] text-slate-500">
          MAE {fmtMetric(param.model.mae)} vs persistence{" "}
          {fmtMetric(param.model.baseline_mae)}
        </p>
      )}
    </div>
  );
}

export default function PredictionCard({ selectedSource }: PredictionCardProps) {
  const stationCode = STATION_BY_SOURCE[selectedSource.name];
  const [horizon, setHorizon] = useState(24);
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!stationCode) {
        setData(null);
        setError("No monitoring station is configured for this source.");
        setLoading(false);
        return;
      }
      const token = getToken();
      if (!token) {
        setData(null);
        setError("Sign in with an authority account to view forecasts.");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const response = await authorityApi.getForecast(
          stationCode,
          token,
          horizon
        );
        if (
          !response ||
          !Array.isArray(response.parameters) ||
          !Array.isArray(response.readiness?.parameters)
        ) {
          // Never render a half-parsed payload as if it were a forecast.
          throw new Error("Forecast service returned an unexpected response.");
        }
        if (!cancelled) setData(response);
      } catch (e) {
        if (!cancelled) {
          setData(null);
          setError(
            e instanceof Error ? e.message : "Forecast request failed."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [stationCode, horizon]);

  const ready = data?.parameters.filter((p) => p.status === "ready") ?? [];

  return (
    <div className="relative overflow-hidden rounded-2xl bg-slate-950 p-6 text-white shadow-md flex flex-col h-full border border-slate-800">
      <div className="absolute -right-12 -top-12 h-36 w-36 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-cyan-500/15 p-2 text-cyan-400 border border-cyan-500/20">
            <LineChart className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white tracking-tight">
              Baseline Forecast
            </h3>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              {stationCode ?? "No station"} • {selectedSource.name}
            </p>
          </div>
        </div>
        <select
          value={horizon}
          onChange={(e) => setHorizon(Number(e.target.value))}
          aria-label="Forecast horizon"
          className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] font-bold text-slate-200 outline-none focus:border-cyan-500"
        >
          {HORIZON_CHOICES.map((h) => (
            <option key={h} value={h}>
              +{h} h
            </option>
          ))}
        </select>
      </div>

      {/* Simulated-history badge */}
      {data?.trained_on_simulated && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3">
          <Database className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
          <p className="text-[11px] leading-relaxed text-amber-300">
            Trained on simulated demo readings — demonstration output, not
            real-world evidence.
          </p>
        </div>
      )}

      {/* Body states */}
      <div className="mt-4 flex-1">
        {loading && (
          <div className="space-y-3 animate-pulse" data-testid="forecast-loading">
            <div className="h-4 w-2/3 rounded bg-slate-800" />
            <div className="h-16 rounded-xl bg-slate-900" />
            <div className="h-16 rounded-xl bg-slate-900" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-xs font-extrabold uppercase tracking-wide text-red-400">
                Forecast unavailable
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              {error}
            </p>
          </div>
        )}

        {!loading && !error && data?.status === "unavailable" && (
          <div>
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                <span className="text-xs font-extrabold uppercase tracking-wide text-amber-400">
                  Forecasting unavailable
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                {data.message}
              </p>
            </div>

            {/* Readiness: the data pipeline reports observed vs required. */}
            <div className="mt-4">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Database className="h-3 w-3" /> History readiness
              </span>
              <div className="mt-2 space-y-1.5">
                {data.readiness.parameters.map((p) => (
                  <div
                    key={p.parameter}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5"
                  >
                    <span className="text-[11px] font-bold capitalize text-slate-300">
                      {p.parameter}
                    </span>
                    <span className="text-[10px] tabular-nums text-slate-400">
                      {p.valid_samples}/{data.readiness.min_samples_required} pts
                      · {p.span_days}/{data.readiness.min_span_days_required} d
                    </span>
                    <span
                      className={`text-[10px] font-extrabold ${
                        p.sufficient ? "text-emerald-400" : "text-amber-400"
                      }`}
                    >
                      {p.sufficient ? "READY" : "NEEDS DATA"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {!loading && !error && data?.status === "ready" && (
          <div>
            <p className="text-xs leading-relaxed text-slate-300">
              {data.message}
            </p>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
              {data.parameters.map((param) => (
                <ParameterRow key={param.parameter} param={param} />
              ))}
            </div>
            {ready.length > 0 && (
              <div className="mt-3 flex items-start gap-2 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                <Clock className="h-3.5 w-3.5 shrink-0 text-cyan-400 mt-0.5" />
                <p className="text-[10px] leading-relaxed text-slate-400">
                  {data.parameters.find((p) => p.status === "ready")?.uncertainty
                    ?.note ?? ""}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer: honesty strip */}
      <div className="mt-4 border-t border-slate-800/80 pt-3 flex items-center justify-between text-[10px] text-slate-500 font-semibold">
        <span className="flex items-center gap-1">
          <BarChart3 className="h-3 w-3" /> Model output — not a measurement
        </span>
        <span className="flex items-center gap-1">
          <Activity className="h-3 w-3" />
          {data ? `generated ${relativeTime(data.generated_at)}` : "not generated"}
        </span>
      </div>
    </div>
  );
}
