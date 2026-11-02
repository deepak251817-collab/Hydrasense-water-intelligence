import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  FlaskConical,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  X,
} from "lucide-react";
import {
  authorityApi,
  simulationApi,
  type ApiError,
  type ForecastParameter,
  type ForecastResponse,
  type MonitoringStation,
  type RecommendationSet,
  type SimulationScenario,
  type SimulationState,
  type StationAlert,
} from "../../lib/api";
import { getToken } from "../../lib/auth";

/**
 * Floating simulation control for every authority page.
 *
 * Reuses the existing simulation API (state / start / pause / generate /
 * reset) and the existing forecast endpoint — it never creates a second
 * simulator. Every generated reading is stored by the backend with
 * `source = "simulator"`; this panel only presents those labelled samples.
 */

const RIVERS = [
  { source_code: "ARKAVATHI", label: "Arkavathi", fallback: "ARK-001" },
  { source_code: "CAUVERY", label: "Cauvery", fallback: "CAU-001" },
  { source_code: "VRISHABHAVATHI", label: "Vrishabhavathi", fallback: "VRS-001" },
] as const;

const SCENARIOS: {
  code: SimulationScenario;
  label: string;
  hint: string;
}[] = [
  { code: "normal", label: "Normal", hint: "Variation around the river baseline" },
  {
    code: "rain_runoff",
    label: "Rain runoff (turbidity up)",
    hint: "First-flush runoff, cloudier water",
  },
  {
    code: "industrial_discharge",
    label: "Industrial discharge (TDS and pH jump)",
    hint: "Alkaline pH, large dissolved load",
  },
  {
    code: "sewage_like",
    label: "Sewage-like (TDS up, pH down)",
    hint: "High TDS with acidic pH",
  },
  {
    code: "sensor_fault",
    label: "Sensor fault (null readings)",
    hint: "One sensor stops reporting (stored as NULL)",
  },
];

const HORIZONS = [6, 12, 24];

interface SourceOption {
  code: string;
  label: string;
}

function errorDetail(err: unknown): string {
  if (err && typeof err === "object") {
    const apiError = err as ApiError;
    return apiError.detail || apiError.message || "Request failed.";
  }
  return "Request failed.";
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString();
}

/** One station per river; ARK-002/003 are additional Arkavathi stations. */
function sourceOptions(stations: MonitoringStation[]): SourceOption[] {
  return RIVERS.map((river) => {
    const match = stations.find(
      (station) =>
        station.is_active &&
        station.water_source?.source_code === river.source_code
    );
    return {
      code: match?.station_code ?? river.fallback,
      label: river.label,
    };
  });
}

const DEFAULT_SOURCES: SourceOption[] = RIVERS.map((river) => ({
  code: river.fallback,
  label: river.label,
}));

function chartData(param: ForecastParameter) {
  return param.points.map((point) => ({
    label: new Date(point.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    value: Number(point.value.toFixed(3)),
    lower: Number(point.lower.toFixed(3)),
    band: Number(Math.max(point.upper - point.lower, 0).toFixed(3)),
  }));
}

export default function SimulationDock() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<SimulationState | null>(null);
  const [sources, setSources] = useState<SourceOption[]>(DEFAULT_SOURCES);
  const [stationCode, setStationCode] = useState<string>("ARK-001");
  const [scenario, setScenario] = useState<SimulationScenario>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<StationAlert[]>([]);
  const [advice, setAdvice] = useState<RecommendationSet | null>(null);
  const [showForecast, setShowForecast] = useState(false);
  const [horizon, setHorizon] = useState(12);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [activeParameter, setActiveParameter] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const next = await simulationApi.getState(token);
      setState(next);
    } catch {
      // The dock must never block the page it floats over.
    }
  }, []);

  // Poll the persistent run so the banner reflects other workers/sessions.
  // The first read is scheduled as a task, so no state is set synchronously
  // from the effect body.
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const initial = window.setTimeout(() => void refreshState(), 0);
    const timer = window.setInterval(() => void refreshState(), 4000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refreshState]);

  // Resolve the three rivers to their seeded stations (falls back to codes).
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let alive = true;
    authorityApi
      .getAllStations(token)
      .then((stations: MonitoringStation[]) => {
        if (!alive) return;
        setSources(sourceOptions(stations));
      })
      .catch(() => {
        // Keep the documented fallback station codes.
      });
    return () => {
      alive = false;
    };
  }, []);

  // Simulated alerts and the shared screening advice are shown here, on
  // screen only. They use the existing authority endpoints.
  useEffect(() => {
    if (!open) return;
    const token = getToken();
    if (!token) return;
    let alive = true;
    authorityApi
      .getAlerts(token, 50)
      .then((response) => {
        if (!alive) return;
        setAlerts(
          response.items.filter(
            (item) => item.source === "simulator" && item.station_code === stationCode
          )
        );
      })
      .catch(() => {
        // The log is advisory; a failed refresh must not break the panel.
      });
    authorityApi
      .getLiveAssessment(stationCode, token, "drinking")
      .then((response) => {
        if (alive) setAdvice(response.assessment.recommendations ?? null);
      })
      .catch(() => {
        // Advice is optional; an unavailable engine must not break the panel.
      });
    return () => {
      alive = false;
    };
  }, [open, stationCode, state?.step]);

  // Forecast uses the existing authority endpoint, including its honest
  // "unavailable" state when history is insufficient. Loaded from the user
  // actions that change the request, never synchronously from an effect.
  const loadForecast = useCallback(async (code: string, hours: number) => {
    const token = getToken();
    if (!token) return;
    setForecastLoading(true);
    setForecastError(null);
    try {
      setForecast(await authorityApi.getForecast(code, token, hours));
    } catch (err) {
      setForecast(null);
      setForecastError(errorDetail(err));
    } finally {
      setForecastLoading(false);
    }
  }, []);

  const onToggleForecast = () => {
    if (showForecast) {
      setShowForecast(false);
      return;
    }
    setShowForecast(true);
    void loadForecast(stationCode, horizon);
  };

  const onHorizonChange = (hours: number) => {
    setHorizon(hours);
    if (showForecast) void loadForecast(stationCode, hours);
  };

  const run = async (action: (token: string) => Promise<SimulationState>) => {
    const token = getToken();
    if (!token) {
      setError("Sign in as an authority user to control the simulation.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setState(await action(token));
    } catch (err) {
      setError(errorDetail(err));
    } finally {
      setBusy(false);
    }
  };

  const onStart = () =>
    run((token) =>
      simulationApi.start(
        { station_code: stationCode, scenario, interval_seconds: 5 },
        token
      )
    );

  const onPause = () => run((token) => simulationApi.pause(token));

  const onGenerate = () =>
    run((token) =>
      simulationApi.generate({ station_code: stationCode, scenario, count: 5 }, token)
    );

  const onReset = async () => {
    await run((token) => simulationApi.reset(token));
    setShowForecast(false);
    setForecast(null);
    setForecastError(null);
    setActiveParameter(null);
    setAlerts([]);
    setAdvice(null);
    setScenario("normal");
  };

  const ready = Array.isArray(forecast?.parameters)
    ? forecast.parameters.filter((p) => p.status === "ready")
    : [];
  const active =
    ready.find((p) => p.parameter === activeParameter) ?? ready[0] ?? null;
  const latest = state?.recent_samples[0] ?? null;
  const running = Boolean(state?.running);

  return (
    <>
      {/* Visible on every authority page while simulation is running. */}
      {running && (
        <div
          role="status"
          className="fixed inset-x-0 bottom-0 z-40 flex h-8 items-center justify-center gap-2 border-t border-amber-300 bg-amber-100 px-3 text-[11px] font-bold text-amber-900"
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          SIMULATION MODE — simulated readings only; never sent by email, SMS or to a
          laboratory.
        </div>
      )}

      {/* Floating trigger */}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="simulation-dock-panel"
        className={`fixed ${running ? "bottom-12" : "bottom-5"} right-5 z-50 inline-flex h-12 items-center gap-2 rounded-full bg-slate-900 px-4 text-xs font-bold text-white shadow-lg ring-1 ring-black/10 transition hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400`}
        title="Open simulation controls"
      >
        {running ? (
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
        ) : (
          <FlaskConical className="h-4 w-4 text-cyan-400" />
        )}
        Simulate
      </button>

      {open && (
        <section
          id="simulation-dock-panel"
          aria-label="Simulation controls"
          className={`fixed ${running ? "bottom-24" : "bottom-20"} right-5 z-50 flex max-h-[78vh] w-[min(26rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl`}
        >
          <header className="flex items-start justify-between gap-3 border-b border-amber-200 bg-amber-50 px-4 py-3">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-extrabold tracking-wide text-amber-900">
                <AlertTriangle className="h-3 w-3" />
                SIMULATION MODE
              </div>
              <h2 className="mt-1 text-sm font-bold text-slate-900">
                Simulated river readings
              </h2>
              <p className="mt-0.5 text-[10px] leading-snug text-amber-800">
                Stored with source = &quot;simulator&quot;. Never mixed with ESP32
                readings and never delivered as a real alert.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close simulation panel"
              className="rounded-lg p-1 text-amber-800 hover:bg-amber-100"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-[10px] font-bold text-slate-600">
                Source
                <select
                  value={stationCode}
                  onChange={(event) => {
                    setStationCode(event.target.value);
                    setActiveParameter(null);
                    if (showForecast) {
                      void loadForecast(event.target.value, horizon);
                    }
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs font-semibold text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
                >
                  {sources.map((source) => (
                    <option key={source.code} value={source.code}>
                      {source.label} ({source.code})
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-[10px] font-bold text-slate-600">
                Scenario
                <select
                  value={scenario}
                  onChange={(event) =>
                    setScenario(event.target.value as SimulationScenario)
                  }
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs font-semibold text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
                >
                  {SCENARIOS.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <p className="text-[10px] font-medium text-slate-500">
              {SCENARIOS.find((item) => item.code === scenario)?.hint}
            </p>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={onStart}
                disabled={busy || !stationCode}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-2 py-2 text-[11px] font-bold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5 text-cyan-400" />
                Start
              </button>
              <button
                type="button"
                onClick={onPause}
                disabled={busy || !running}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Pause className="h-3.5 w-3.5 text-slate-500" />
                Pause
              </button>
              <button
                type="button"
                onClick={onGenerate}
                disabled={busy || !stationCode}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-cyan-200 bg-cyan-50 px-2 py-2 text-[11px] font-bold text-cyan-800 hover:bg-cyan-100 disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Generate next batch
              </button>
              <button
                type="button"
                onClick={onReset}
                disabled={busy}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <RotateCcw className="h-3.5 w-3.5 text-slate-500" />
                Reset
              </button>
            </div>

            {error && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-2 py-1.5 text-[10px] font-semibold text-red-700">
                {error}
              </p>
            )}

            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
              <span>
                Status:{" "}
                <strong className={running ? "text-emerald-600" : "text-slate-700"}>
                  {running ? "running" : "paused"}
                </strong>
              </span>
              <span>
                Samples: <strong className="text-slate-800">{state?.samples_generated ?? 0}</strong>
              </span>
              <span>
                Last:{" "}
                <strong className="text-slate-800">
                  {formatTime(state?.last_sample_at ?? null)}
                </strong>
              </span>
            </div>

            {latest && (
              <div className="grid grid-cols-4 gap-1 rounded-xl border border-slate-200 bg-slate-50 p-2 text-center">
                {[
                  ["pH", latest.ph ?? "NULL"],
                  ["TDS", latest.tds ?? "NULL"],
                  ["°C", latest.temperature ?? "NULL"],
                  ["Index", latest.turbidity_index ?? "NULL"],
                ].map(([label, value]) => (
                  <div key={label}>
                    <div className="text-[9px] font-bold uppercase text-slate-400">
                      {label}
                    </div>
                    <div className="text-xs font-extrabold text-slate-800">{value}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-xl border border-slate-200">
              <button
                type="button"
                onClick={onToggleForecast}
                className="flex w-full items-center justify-between px-3 py-2 text-left"
                aria-expanded={showForecast}
              >
                <span className="text-[11px] font-bold text-slate-700">
                  Show forecast
                </span>
                <span className="text-[10px] font-semibold text-slate-400">
                  next {horizon} h
                </span>
              </button>

              {showForecast && (
                <div className="border-t border-slate-100 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[9px] font-extrabold text-amber-800">
                      SIMULATED INPUT
                    </span>
                    <div className="flex gap-1">
                      {HORIZONS.map((hours) => (
                        <button
                          key={hours}
                          type="button"
                          onClick={() => onHorizonChange(hours)}
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            horizon === hours
                              ? "bg-slate-900 text-white"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {hours} h
                        </button>
                      ))}
                    </div>
                  </div>

                  {forecastLoading && (
                    <p className="mt-2 text-[10px] font-semibold text-slate-400">
                      Loading forecast…
                    </p>
                  )}

                  {!forecastLoading && forecastError && (
                    <p className="mt-2 text-[10px] font-semibold text-red-600">
                      {forecastError}
                    </p>
                  )}

                  {!forecastLoading &&
                    !forecastError &&
                    forecast?.status === "unavailable" && (
                      <div className="mt-2 space-y-1">
                        <p className="text-[10px] leading-snug text-slate-600">
                          {forecast.message}
                        </p>
                        <p className="text-[9px] text-slate-400">
                          Needs {forecast.readiness.min_samples_required} points over{" "}
                          {forecast.readiness.min_span_days_required} days — history so
                          far spans {forecast.readiness.observed_span_days} days.
                        </p>
                      </div>
                    )}

                  {!forecastLoading &&
                    !forecastError &&
                    forecast?.status === "ready" &&
                    ready.length > 0 && (
                      <div className="mt-2">
                        <div className="flex flex-wrap gap-1">
                          {ready.map((param) => (
                            <button
                              key={param.parameter}
                              type="button"
                              onClick={() => setActiveParameter(param.parameter)}
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                active?.parameter === param.parameter
                                  ? "bg-cyan-600 text-white"
                                  : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {param.label}
                            </button>
                          ))}
                        </div>

                        {active && (
                          <>
                            <p className="mt-2 text-[10px] font-bold text-slate-700">
                              Prediction — next {horizon} h
                            </p>
                            <div data-testid="simulation-forecast-chart">
                              <AreaChart
                                width={344}
                                height={150}
                                data={chartData(active)}
                                margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
                              >
                                <CartesianGrid
                                  strokeDasharray="3 3"
                                  stroke="#e2e8f0"
                                  vertical={false}
                                />
                                <XAxis
                                  dataKey="label"
                                  tick={{ fontSize: 9 }}
                                  interval="preserveStartEnd"
                                />
                                <YAxis tick={{ fontSize: 9 }} domain={["auto", "auto"]} />
                                <Tooltip contentStyle={{ fontSize: 10 }} />
                                <Area
                                  type="monotone"
                                  dataKey="lower"
                                  stackId="band"
                                  stroke="none"
                                  fill="transparent"
                                  isAnimationActive={false}
                                />
                                <Area
                                  type="monotone"
                                  dataKey="band"
                                  stackId="band"
                                  stroke="none"
                                  fill="#06b6d4"
                                  fillOpacity={0.25}
                                  isAnimationActive={false}
                                />
                                <Line
                                  type="monotone"
                                  dataKey="value"
                                  stroke="#0891b2"
                                  strokeWidth={2}
                                  dot={false}
                                  isAnimationActive={false}
                                />
                              </AreaChart>
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-3 text-[9px] font-semibold text-slate-500">
                              <span className="inline-flex items-center gap-1">
                                <span className="h-0.5 w-3 bg-cyan-600" /> Prediction
                              </span>
                              <span className="inline-flex items-center gap-1">
                                <span className="h-2 w-3 bg-cyan-200" /> Uncertainty band
                              </span>
                              <span>{active.unit}</span>
                            </div>
                            <p className="mt-1 text-[9px] leading-snug text-slate-400">
                              {active.uncertainty?.note ??
                                "Model output — not a measurement."}
                            </p>
                          </>
                        )}
                      </div>
                    )}
                </div>
              )}
            </div>

            <div>
              <h3 className="text-[11px] font-bold text-slate-700">
                Recommendation (simulated){" "}
                <span className="font-semibold text-slate-400">
                  {advice?.urgency ? `${advice.urgency} urgency` : "no concern"}
                </span>
              </h3>
              <p className="mt-0.5 text-[9px] leading-snug text-slate-400">
                Shared screening rules, fed by the simulated reading — advisory
                only, never a laboratory or compliance verdict.
              </p>
              <ul className="mt-1 space-y-1">
                {(advice?.recommendations ?? []).slice(0, 2).map((item) => (
                  <li
                    key={`${item.parameter}-${item.direction}`}
                    className="rounded-lg border border-cyan-100 bg-cyan-50/60 px-2 py-1.5"
                  >
                    <span className="text-[10px] font-bold text-slate-700">
                      {item.label} — {item.direction.replace(/_/g, " ")}
                    </span>
                    <p className="mt-0.5 text-[9px] leading-snug text-slate-500">
                      {item.actions[0] ?? "Review the reading before use."}
                    </p>
                  </li>
                ))}
                {(advice?.recommendations ?? []).length === 0 && (
                  <li className="rounded-lg border border-dashed border-slate-200 px-2 py-2 text-[9px] text-slate-400">
                    No advisory rule triggered for the current simulated reading.
                  </li>
                )}
              </ul>
            </div>

            <div>
              <h3 className="text-[11px] font-bold text-slate-700">
                Alert log{" "}
                <span className="font-semibold text-slate-400">(on-screen only)</span>
              </h3>
              <p className="mt-0.5 text-[9px] leading-snug text-slate-400">
                Simulated alerts are summarised here. No email, SMS or laboratory
                message is sent for simulated readings.
              </p>
              <ul className="mt-1 space-y-1">
                {alerts.slice(0, 5).map((alert, index) => (
                  <li
                    key={`${alert.parameter}-${alert.timestamp}-${index}`}
                    className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5"
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          alert.severity === "critical"
                            ? "bg-red-500"
                            : "bg-amber-500"
                        }`}
                      />
                      <span className="text-[10px] font-bold text-slate-700">
                        {alert.label}
                      </span>
                      <span className="text-[9px] font-semibold uppercase text-slate-400">
                        {alert.severity}
                      </span>
                      <span className="ml-auto text-[9px] text-slate-400">
                        {formatTime(alert.timestamp)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[9px] leading-snug text-slate-500">
                      {alert.value === null
                        ? "Not reporting (NULL)"
                        : `${alert.value} ${alert.unit}`}{" "}
                      — {alert.message}
                    </p>
                  </li>
                ))}
                {alerts.length === 0 && (
                  <li className="rounded-lg border border-dashed border-slate-200 px-2 py-2 text-[9px] text-slate-400">
                    No simulated alerts for this station yet. Generate samples with a
                    spill scenario to see them.
                  </li>
                )}
              </ul>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
