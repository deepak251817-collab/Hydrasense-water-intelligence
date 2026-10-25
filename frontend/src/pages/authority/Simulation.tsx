import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Play,
  Pause,
  RefreshCw,
  AlertTriangle,
  Waves,
  FlaskConical,
  Activity,
} from "lucide-react";
import { getToken } from "../../lib/auth";
import {
  authorityApi,
  simulationApi,
  type ApiError,
  type MonitoringStation,
  type SimulationScenario,
  type SimulationState,
} from "../../lib/api";

/** Fetch failures are thrown as plain ApiError-shaped objects. */
function errorDetail(err: unknown): string {
  if (err && typeof err === "object") {
    const apiError = err as ApiError;
    return apiError.detail || apiError.message || "Request failed.";
  }
  return "Request failed.";
}

const SCENARIOS: { code: SimulationScenario; label: string; hint: string }[] = [
  { code: "normal", label: "Normal", hint: "Realistic variation around the river baseline" },
  { code: "gradual_deterioration", label: "Gradual Deterioration", hint: "Steady drift to cloudier, higher-TDS water" },
  { code: "sudden_change", label: "Sudden Change", hint: "Stable, then an abrupt step change" },
  { code: "sensor_fault", label: "Sensor Fault", hint: "A sensor stops reporting (stored as NULL)" },
];

function turbidityBand(index: number | null): string {
  if (index === null) return "—";
  if (index < 30) return "CLEARER";
  if (index < 55) return "MODERATE";
  return "CLOUDIER";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString();
}

export default function Simulation() {
  const [stations, setStations] = useState<MonitoringStation[]>([]);
  const [stationCode, setStationCode] = useState<string>("");
  const [scenario, setScenario] = useState<SimulationScenario>("normal");
  const [seed, setSeed] = useState<string>("");
  const [intervalSeconds, setIntervalSeconds] = useState<string>("5");
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const next = await simulationApi.getState(token);
      setState(next);
      if (next.station_code && !stationCode) setStationCode(next.station_code);
      if (next.scenario) setScenario(next.scenario as SimulationScenario);
      setError(null);
    } catch (err) {
      setError(errorDetail(err));
    }
  }, [stationCode]);

  // Load stations once, then poll the simulation state while mounted.
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    authorityApi
      .getAllStations(token)
      .then((data: MonitoringStation[]) => {
        setStations(data);
        if (data.length > 0) setStationCode((current) => current || data[0].station_code);
      })
      .catch(() => setError("Could not load monitoring stations."))
      .finally(() => {
        // Kick off the first state read inside a promise callback, then poll.
        void refresh();
        timer.current = window.setInterval(() => void refresh(), 3000);
      });
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [refresh]);

  const run = async (action: () => Promise<SimulationState>) => {
    const token = getToken();
    if (!token) {
      setError("Sign in as an authority user to control the simulation.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setState(await action());
    } catch (err) {
      setError(errorDetail(err));
    } finally {
      setLoading(false);
    }
  };

  const onStart = () =>
    run(() =>
      simulationApi.start(
        {
          station_code: stationCode,
          scenario,
          seed: seed.trim() === "" ? null : Number(seed),
          interval_seconds: Number(intervalSeconds) > 0 ? Number(intervalSeconds) : 5,
        },
        getToken() as string
      )
    );

  const onPause = () => run(() => simulationApi.pause(getToken() as string));

  const onGenerate = (count = 1) =>
    run(() =>
      simulationApi.generate(
        {
          station_code: stationCode || undefined,
          scenario,
          seed: seed.trim() === "" ? null : Number(seed),
          count,
        },
        getToken() as string
      )
    );

  const latest = state?.recent_samples[0] ?? null;
  const cards = [
    { label: "pH", value: latest?.ph, unit: "pH", icon: FlaskConical },
    { label: "TDS", value: latest?.tds, unit: "mg/L", icon: Activity },
    { label: "Temperature", value: latest?.temperature, unit: "°C", icon: Activity },
    {
      label: "Turbidity Index",
      value: latest?.turbidity_index,
      unit: "0–100 (not NTU)",
      icon: Waves,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-800 border border-amber-300">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>SIMULATED DATA — NOT LIVE SENSOR DATA</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            River Simulation
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Generate labelled demonstration samples for the three configured rivers —
            Arkavathi, Cauvery and Vrishabhavathi — using exactly the four supported
            sensors (pH, TDS, temperature, turbidity index).
          </p>
        </div>
        <Link
          to="/authority/monitoring"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
        >
          <Activity className="h-4 w-4 text-cyan-600" />
          Open Live Monitoring
        </Link>
      </div>

      {/* Controls */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs font-bold text-slate-600">
            Monitoring station
            <select
              value={stationCode}
              onChange={(event) => setStationCode(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
            >
              {stations.length === 0 && <option value="">No stations available</option>}
              {stations.map((station) => (
                <option key={station.station_code} value={station.station_code}>
                  {station.station_name} ({station.station_code})
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-bold text-slate-600">
            Scenario
            <select
              value={scenario}
              onChange={(event) => setScenario(event.target.value as SimulationScenario)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
            >
              {SCENARIOS.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[11px] font-medium text-slate-400">
              {SCENARIOS.find((item) => item.code === scenario)?.hint}
            </span>
          </label>

          <label className="block text-xs font-bold text-slate-600">
            Random seed (optional, reproducible)
            <input
              type="number"
              value={seed}
              placeholder="e.g. 42"
              onChange={(event) => setSeed(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
            />
          </label>

          <label className="block text-xs font-bold text-slate-600">
            Interval (seconds)
            <input
              type="number"
              min={1}
              value={intervalSeconds}
              onChange={(event) => setIntervalSeconds(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onStart}
            disabled={loading || !stationCode}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            <Play className="h-4 w-4 text-cyan-400" />
            Start Simulation
          </button>
          <button
            type="button"
            onClick={onPause}
            disabled={loading || !state?.running}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <Pause className="h-4 w-4 text-slate-500" />
            Pause Simulation
          </button>
          <button
            type="button"
            onClick={() => onGenerate(1)}
            disabled={loading || !stationCode}
            className="inline-flex items-center gap-2 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-2 text-xs font-bold text-cyan-800 hover:bg-cyan-100 disabled:opacity-50"
          >
            <RefreshCw className="h-4 w-4" />
            Generate Sample
          </button>
          <button
            type="button"
            onClick={() => onGenerate(5)}
            disabled={loading || !stationCode}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Generate 5 Samples
          </button>

          <span
            className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
              state?.running
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-slate-100 text-slate-600 border border-slate-200"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                state?.running ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
              }`}
            />
            {state?.running ? "Simulation running" : "Simulation paused"}
          </span>
        </div>

        {error && (
          <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
            {error}
          </p>
        )}

        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
          <span>Samples generated: <strong className="text-slate-800">{state?.samples_generated ?? 0}</strong></span>
          <span>Step: <strong className="text-slate-800">{state?.step ?? 0}</strong></span>
          <span>Last sample: <strong className="text-slate-800">{formatTime(state?.last_sample_at ?? null)}</strong></span>
          <span>Scenario: <strong className="text-slate-800">{SCENARIOS.find((item) => item.code === scenario)?.label ?? scenario}</strong></span>
        </div>
      </div>

      {/* Latest four sensor readings */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div key={card.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center gap-2 mb-3">
              <card.icon className="h-4 w-4 text-cyan-600" />
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                {card.label}
              </span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900">
              {card.value ?? "—"}
              <span className="ml-1 text-xs font-semibold text-slate-400">{card.unit}</span>
            </p>
            <p className="text-xs mt-1 font-semibold text-slate-500">
              {card.label === "Turbidity Index"
                ? `Band: ${turbidityBand(latest?.turbidity_index ?? null)} (higher = cloudier)`
                : "Simulated demonstration value"}
            </p>
          </div>
        ))}
      </div>

      {latest?.fault_sensor && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs font-semibold text-amber-800">
          Sensor fault scenario: the {latest.fault_sensor} sensor is not reporting and the
          value is stored as NULL — no number is fabricated for a failed sensor.
        </div>
      )}

      {/* Recent samples */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="font-bold text-slate-900">Recent simulated samples</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Stored with source = "simulator" and label SIMULATED DATA — NOT LIVE SENSOR DATA.
              Generated readings feed the same pipeline as hardware telemetry, so trends,
              screening results and alerts update from them.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-1 text-[10px] font-bold text-amber-800">
            <AlertTriangle className="h-3 w-3" />
            SIMULATED
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-100">
                <th className="px-5 py-2.5 font-bold">Time</th>
                <th className="px-3 py-2.5 font-bold">Station</th>
                <th className="px-3 py-2.5 font-bold">Scenario</th>
                <th className="px-3 py-2.5 font-bold">pH</th>
                <th className="px-3 py-2.5 font-bold">TDS (mg/L)</th>
                <th className="px-3 py-2.5 font-bold">Temp (°C)</th>
                <th className="px-3 py-2.5 font-bold">Turbidity index</th>
                <th className="px-3 py-2.5 font-bold">Fault</th>
              </tr>
            </thead>
            <tbody>
              {(state?.recent_samples ?? []).length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-6 text-center text-slate-400">
                    No samples yet — press Start Simulation or Generate Sample.
                  </td>
                </tr>
              )}
              {(state?.recent_samples ?? []).map((sample) => (
                <tr key={sample.id} className="border-b border-slate-50 text-slate-700">
                  <td className="px-5 py-2.5 font-medium">{formatTime(sample.timestamp)}</td>
                  <td className="px-3 py-2.5">{sample.station_code}</td>
                  <td className="px-3 py-2.5">{sample.scenario}</td>
                  <td className="px-3 py-2.5">{sample.ph ?? "NULL"}</td>
                  <td className="px-3 py-2.5">{sample.tds ?? "NULL"}</td>
                  <td className="px-3 py-2.5">{sample.temperature ?? "NULL"}</td>
                  <td className="px-3 py-2.5">
                    {sample.turbidity_index ?? "NULL"}
                    {sample.turbidity_index !== null && (
                      <span className="ml-1 text-[10px] text-slate-400">
                        ({turbidityBand(sample.turbidity_index)})
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-amber-700">{sample.fault_sensor ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
