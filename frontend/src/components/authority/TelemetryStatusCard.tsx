import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Cpu,
  Droplets,
  Radio,
  RefreshCw,
  Thermometer,
  Wifi,
  WifiOff,
  Wind,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type {
  DeviceDiagnostics,
  LatestReading,
  SensorDiagnostics,
  StationReading,
} from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";

const POLL_INTERVAL_MS = 5000;
const ONLINE_AFTER_MS = 15000; // healthy link: a few publish cycles missed at most
const STALE_AFTER_MS = 5 * 60 * 1000; // > 5 min silent = offline
const HISTORY_LIMIT = 50;
const HISTORY_POINTS = 30;

/** firmware unit tag for the ESP32 provisional relative index. */
const TURBIDITY_UNIT_RELATIVE = "relative_index_0_100";
const TURBIDITY_BANDS = ["CLEARER", "MODERATE", "CLOUDIER"] as const;

type LinkStatus = "online" | "stale" | "offline" | "no-data" | "unauthorized" | "error";
type HistoryStatus = "loading" | "ready" | "empty" | "error";

/**
 * Unit of a turbidity value. Never assume NTU: an unknown unit is its own
 * state, because legacy rows predate unit tracking.
 */
type TurbidityUnit = "relative_index_0_100" | "ntu" | "unknown";

function resolveTurbidityUnit(
  reading: LatestReading | null,
  diag: SensorDiagnostics | null
): TurbidityUnit {
  const tagged = reading?.turbidity_unit ?? diag?.unit ?? null;
  if (tagged === TURBIDITY_UNIT_RELATIVE) return TURBIDITY_UNIT_RELATIVE;
  if (tagged === "ntu") return "ntu";
  return "unknown";
}

/** Firmware status band, only valid for relative-index readings. */
function resolveTurbidityStatus(
  reading: LatestReading | null,
  diag: SensorDiagnostics | null
): (typeof TURBIDITY_BANDS)[number] | null {
  if (resolveTurbidityUnit(reading, diag) !== TURBIDITY_UNIT_RELATIVE) return null;
  const raw = reading?.turbidity_status ?? diag?.relative_status ?? null;
  if (typeof raw !== "string") return null;
  const normalized = raw.trim().toUpperCase();
  return (TURBIDITY_BANDS as readonly string[]).includes(normalized)
    ? (normalized as (typeof TURBIDITY_BANDS)[number])
    : null;
}

const TURBIDITY_STATUS_STYLES: Record<
  (typeof TURBIDITY_BANDS)[number],
  { cls: string; hint: string }
> = {
  CLEARER: {
    cls: "bg-sky-50 text-sky-700 border-sky-200",
    hint: "Device band: clearer than the provisional cloudy reference",
  },
  MODERATE: {
    cls: "bg-amber-50 text-amber-700 border-amber-200",
    hint: "Device band: between the provisional clear and cloudy references",
  },
  CLOUDIER: {
    cls: "bg-orange-50 text-orange-700 border-orange-200",
    hint: "Device band: at or beyond the provisional cloudy reference",
  },
};

interface TelemetryStatusCardProps {
  /** Backend station code (e.g. "ARK-001"), from the station selector. */
  stationCode: string | null;
}

function ageMs(iso: string): number | null {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Date.now() - t;
}

function formatAge(ms: number): string {
  if (ms < 1000) return "just now";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

function formatUptime(ms: number | undefined): string {
  if (ms === undefined) return "—";
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function sensorEntry(
  diagnostics: DeviceDiagnostics | null,
  key: string
): SensorDiagnostics | null {
  if (!diagnostics) return null;
  const entry = diagnostics[key];
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
  return entry as SensorDiagnostics;
}

/** The `device` diagnostics entry (uptime / RSSI / seq / errors). */
function deviceEntry(diagnostics: DeviceDiagnostics | null): DeviceDiagnostics | null {
  if (!diagnostics) return null;
  const entry = diagnostics["device"];
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
  return entry as unknown as DeviceDiagnostics;
}

/**
 * Live hardware telemetry panel (authority dashboard).
 *
 * Shows the LATEST RAW READING from the backend for the selected station:
 * link status + last-reading age, data provenance (physical ESP32 vs
 * simulator), calibrated values when they exist, and raw ADC/voltage +
 * calibration status per sensor. NULL values render as "Uncalibrated" or
 * "Sensor failed" — never as fabricated numbers and never as "Safe".
 */
/**
 * The panel is keyed by station code, so switching stations resets all state
 * naturally instead of clearing it synchronously inside an effect.
 */
export default function TelemetryStatusCard({ stationCode }: TelemetryStatusCardProps) {
  return <TelemetryStatusPanel key={stationCode ?? "no-station"} stationCode={stationCode} />;
}

function TelemetryStatusPanel({ stationCode }: TelemetryStatusCardProps) {
  const [reading, setReading] = useState<LatestReading | null>(null);
  const [status, setStatus] = useState<LinkStatus>("no-data");
  const [message, setMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<StationReading[]>([]);
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>("loading");
  const timerRef = useRef<number | null>(null);

  const fetchLatest = useCallback(async () => {
    if (!stationCode) return;
    const token = getToken();
    if (!token) {
      setStatus("unauthorized");
      setMessage("Sign in with an authority account to view hardware telemetry.");
      return;
    }
    try {
      const data = await authorityApi.getLatestReading(stationCode, token);
      setReading(data);
      setMessage(null);
      const age = ageMs(data.timestamp);
      if (age === null) setStatus("error");
      else if (age < ONLINE_AFTER_MS) setStatus("online");
      else if (age < STALE_AFTER_MS) setStatus("stale");
      else setStatus("offline");

      // Reading history is fetched independently: a history failure must not
      // hide the latest reading (and vice versa).
      try {
        const rows = await authorityApi.getStationReadings(
          stationCode,
          token,
          HISTORY_LIMIT
        );
        setHistory(rows);
        setHistoryStatus(rows.length > 0 ? "ready" : "empty");
      } catch {
        setHistory([]);
        setHistoryStatus("error");
      }
    } catch (err) {
      const apiErr = err as { statusCode?: number; detail?: string };
      if (apiErr.statusCode === 404) {
        setReading(null);
        setStatus("no-data");
        setMessage("No readings received for this station yet.");
      } else if (apiErr.statusCode === 401 || apiErr.statusCode === 403) {
        setStatus("unauthorized");
        setMessage("Your account is not authorized to view hardware telemetry.");
      } else {
        setStatus("error");
        setMessage(apiErr.detail || "Failed to reach the backend API.");
      }
    }
  }, [stationCode]);

  useEffect(() => {
    // Kick the first fetch on the next tick (state updates never run
    // synchronously inside the effect body) and poll afterwards.
    const initialId = window.setTimeout(fetchLatest, 0);
    timerRef.current = window.setInterval(fetchLatest, POLL_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialId);
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [fetchLatest]);

  const diagnostics = reading?.diagnostics ?? null;
  const phDiag = sensorEntry(diagnostics, "ph");
  const tdsDiag = sensorEntry(diagnostics, "tds");
  const turbDiag = sensorEntry(diagnostics, "turbidity");
  const tempDiag = sensorEntry(diagnostics, "temperature");
  const deviceDiag = deviceEntry(diagnostics);

  const isHardware = reading?.source === "esp32";
  // Turbidity's meaning is driven by its stored unit — never assumed NTU.
  const turbUnit = resolveTurbidityUnit(reading, turbDiag);
  const turbIsIndex = turbUnit === TURBIDITY_UNIT_RELATIVE;
  const turbStatus = resolveTurbidityStatus(reading, turbDiag);
  const lastAge = reading ? ageMs(reading.timestamp) : null;

  // History: only rows that are explicitly RELATIVE INDEX readings may be
  // plotted as an index. NTU rows and rows with an unknown unit are excluded
  // so two different quantities never share one axis.
  const relativeHistory = history
    .filter((r) => r.turbidity_unit === TURBIDITY_UNIT_RELATIVE && r.turbidity !== null)
    .slice(0, HISTORY_POINTS)
    .slice()
    .reverse();
  const excludedHistoryCount = history.length - relativeHistory.length;
  const chartData = relativeHistory.map((r) => ({
    time: new Date(r.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    index: r.turbidity as number,
    status: r.turbidity_status ?? null,
    timestamp: r.timestamp,
  }));

  const linkBadge =
    status === "online"
      ? { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", label: "Online" }
      : status === "stale"
        ? { cls: "bg-amber-50 text-amber-700 border-amber-200", label: "Stale" }
        : status === "offline"
          ? { cls: "bg-red-50 text-red-700 border-red-200", label: "Offline" }
          : status === "no-data"
            ? { cls: "bg-slate-50 text-slate-600 border-slate-200", label: "No data" }
            : status === "unauthorized"
              ? { cls: "bg-amber-50 text-amber-700 border-amber-200", label: "Unauthorized" }
              : { cls: "bg-red-50 text-red-700 border-red-200", label: "Error" };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs" data-testid="telemetry-status">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Cpu className="h-4.5 w-4.5 text-slate-700" />
          <div>
            <h3 className="text-sm font-bold text-slate-900">Station Telemetry</h3>
            <p className="text-[11px] text-slate-400 font-medium">
              Latest raw reading from the station device
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${linkBadge.cls}`}
            data-testid="telemetry-link-status"
          >
            {status === "online" || status === "stale" ? (
              <Wifi className="h-3 w-3" />
            ) : (
              <WifiOff className="h-3 w-3" />
            )}
            {linkBadge.label}
          </span>
          <button
            onClick={fetchLatest}
            aria-label="Refresh telemetry"
            className="rounded-lg border border-slate-200 p-1.5 text-slate-400 hover:text-slate-700 hover:border-slate-300 transition-colors"
            data-testid="telemetry-refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {(status === "unauthorized" || status === "error" || status === "no-data") && (
        <p
          className={`mt-4 text-sm rounded-xl p-4 ${
            status === "error"
              ? "text-red-800 bg-red-50 border border-red-200"
              : "text-slate-500 bg-slate-50 border border-slate-100"
          }`}
        >
          {message}
        </p>
      )}

      {reading && (status === "online" || status === "stale" || status === "offline") && (
        <div className="mt-4 space-y-4">
          {/* Provenance + link info */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-bold uppercase tracking-wider ${
                isHardware
                  ? "bg-cyan-50 text-cyan-800 border-cyan-200"
                  : "bg-slate-50 text-slate-600 border-slate-200"
              }`}
              data-testid="telemetry-source"
            >
              <Radio className="h-3 w-3" />
              {isHardware ? "Physical hardware (ESP32)" : "Simulated"}
            </span>
            <span>
              Device: <strong className="font-mono text-slate-700">{reading.device_id}</strong>
            </span>
            <span>
              Last reading:{" "}
              <strong className="text-slate-700" data-testid="telemetry-last-reading">
                {lastAge !== null ? formatAge(lastAge) : "unknown"}
              </strong>{" "}
              · {new Date(reading.timestamp).toLocaleTimeString()}
            </span>
            {diagnostics?.device && typeof diagnostics.device === "object" && (
              <>
                <span>
                  Wi-Fi RSSI:{" "}
                  <strong className="text-slate-700">
                    {"wifi_rssi_dbm" in diagnostics.device
                      ? `${diagnostics.device.wifi_rssi_dbm} dBm`
                      : "—"}
                  </strong>
                </span>
                <span>
                  Uptime:{" "}
                  <strong className="text-slate-700">
                    {formatUptime(
                      "uptime_ms" in diagnostics.device
                        ? (diagnostics.device.uptime_ms as number)
                        : undefined
                    )}
                  </strong>
                </span>
              </>
            )}
          </div>

          {/* Sensor values: calibrated value OR honest "uncalibrated/failed" state */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <ValueTile
              label="pH"
              icon={<Droplets className="h-4 w-4" />}
              value={reading.pH}
              unit=""
              diag={phDiag}
              nullLabel="Uncalibrated"
            />
            <ValueTile
              label={turbIsIndex ? "Relative Turbidity Index" : "Turbidity"}
              icon={<Wind className="h-4 w-4" />}
              value={reading.turbidity}
              unit={
                turbIsIndex
                  ? " / 100"
                  : turbUnit === "ntu"
                    ? " NTU"
                    : " (unit unknown)"
              }
              diag={turbDiag}
              nullLabel="Uncalibrated"
              statusBadge={
                turbIsIndex && turbStatus ? (
                  <TurbidityStatusPill status={turbStatus} />
                ) : undefined
              }
              footnote={
                turbIsIndex
                  ? "Provisional relative index — not NTU"
                  : turbUnit === "unknown"
                    ? "Unit not recorded for this reading"
                    : undefined
              }
            />
            <ValueTile
              label="TDS"
              icon={<Droplets className="h-4 w-4" />}
              value={reading.tds}
              unit=" mg/L"
              diag={tdsDiag}
              nullLabel="Uncalibrated"
            />
            <ValueTile
              label="Temperature"
              icon={<Thermometer className="h-4 w-4" />}
              value={reading.temperature}
              unit="°C"
              diag={tempDiag}
              nullLabel="Sensor failed"
            />
          </div>

          {/* Raw sensor data + calibration status (hardware diagnostics) */}
          {isHardware && diagnostics && (
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                Raw sensor data (uncalibrated — not engineering values)
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px] font-mono text-slate-600">
                  <thead>
                    <tr className="text-left text-slate-400">
                      <th className="py-1 pr-4 font-semibold">Sensor</th>
                      <th className="py-1 pr-4 font-semibold">Raw ADC</th>
                      <th className="py-1 pr-4 font-semibold">Voltage</th>
                      <th className="py-1 font-semibold">Calibration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["pH", phDiag],
                        ["TDS", tdsDiag],
                        ["Turbidity", turbDiag],
                      ] as const
                    ).map(([name, diag]) => (
                      <tr key={name} className="border-t border-slate-100">
                        <td className="py-1 pr-4 font-bold text-slate-700">{name}</td>
                        <td className="py-1 pr-4">{diag?.raw_adc ?? "—"}</td>
                        <td className="py-1 pr-4">
                          {diag?.voltage_v !== undefined ? `${diag.voltage_v} V` : "—"}
                        </td>
                        <td className="py-1">
                          <CalibrationBadge status={diag?.calibration_status ?? null} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {typeof tempDiag?.valid === "boolean" && !tempDiag.valid && (
                <p className="mt-2 text-[11px] text-red-600 flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  DS18B20 temperature sensor fault: {tempDiag.error || "invalid reading"}.
                </p>
              )}
            </div>
          )}

          {/* Relative turbidity history — ONLY unit-tagged index readings.
              NTU rows and unknown-unit rows are never plotted on this axis. */}
          <div
            className="rounded-xl border border-slate-100 bg-slate-50 p-4"
            data-testid="turbidity-history"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Relative Turbidity Index History (0–100)
              </p>
              <span className="text-[10px] font-semibold text-slate-400">
                Higher = cloudier · not NTU
              </span>
            </div>

            {historyStatus === "loading" && (
              <p className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-500">
                <RefreshCw className="h-3 w-3 animate-spin" /> Loading reading history…
              </p>
            )}

            {historyStatus === "error" && (
              <p className="mt-2 text-[11px] text-amber-700">
                Reading history is unavailable right now. The latest reading above is
                unaffected.
              </p>
            )}

            {historyStatus !== "loading" && relativeHistory.length === 0 && (
              <p className="mt-2 text-[11px] text-slate-500">
                No relative-index readings yet. NTU or unknown-unit readings are not shown
                here.
              </p>
            )}

            {relativeHistory.length > 0 && (
              <>
                <div className="mt-3 h-40 w-full" data-testid="turbidity-history-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        vertical={false}
                        stroke="#e2e8f0"
                      />
                      <XAxis
                        dataKey="time"
                        tick={{ fontSize: 10, fill: "#94a3b8" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        domain={[0, 100]}
                        ticks={[0, 25, 50, 75, 100]}
                        tick={{ fontSize: 10, fill: "#94a3b8" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<TurbidityTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="index"
                        stroke="#0ea5e9"
                        strokeWidth={2}
                        dot={{ r: 2.5 }}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="mt-2 max-h-32 overflow-y-auto" data-testid="turbidity-history-rows">
                  <table className="w-full text-[11px] font-mono text-slate-600">
                    <thead>
                      <tr className="text-left text-slate-400">
                        <th className="py-1 pr-3 font-semibold">Time</th>
                        <th className="py-1 pr-3 font-semibold">Index</th>
                        <th className="py-1 font-semibold">Band</th>
                      </tr>
                    </thead>
                    <tbody>
                      {relativeHistory
                        .slice(-10)
                        .reverse()
                        .map((row) => (
                          <tr key={row.id} className="border-t border-slate-100">
                            <td className="py-1 pr-3">
                              {new Date(row.timestamp).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                              })}
                            </td>
                            <td className="py-1 pr-3 font-bold text-slate-700">
                              {typeof row.turbidity === "number"
                                ? `${row.turbidity.toFixed(1)} / 100`
                                : "—"}
                            </td>
                            <td className="py-1">
                              {row.turbidity_status ? row.turbidity_status : "—"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>

                <p className="mt-2 text-[10px] text-slate-400">
                  Showing {relativeHistory.length} relative-index reading
                  {relativeHistory.length === 1 ? "" : "s"} from station{" "}
                  <span className="font-mono font-bold">{reading.station_code}</span>
                  {excludedHistoryCount > 0
                    ? ` · ${excludedHistoryCount} NTU/unknown-unit reading(s) excluded (different unit)`
                    : ""}
                </p>
              </>
            )}
          </div>

          {/* Device-reported errors */}
          {diagnostics && Array.isArray(deviceDiag?.errors) && deviceDiag.errors.length > 0 && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-red-700 mb-1.5 flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" /> Device errors
              </p>
              <ul className="text-[11px] text-red-700 font-mono space-y-0.5">
                {deviceDiag.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Honesty footnote */}
          <p className="text-[11px] text-slate-400 flex items-start gap-1.5">
            <Activity className="h-3.5 w-3.5 mt-px shrink-0" />
            Uncalibrated sensors report raw ADC/voltage only — no pH, NTU or ppm value is
            assumed until reference calibration is performed. The relative turbidity index is
            a provisional 0–100 scale (higher = cloudier), not NTU, and neither index nor NTU
            alone means the water is safe. NULL values never mean "safe".
            {deviceDiag && "seq" in deviceDiag ? (
              <span className="font-mono"> · seq {String(deviceDiag.seq)}</span>
            ) : null}
          </p>
        </div>
      )}
    </div>
  );
}

function TurbidityStatusPill({
  status,
}: {
  status: (typeof TURBIDITY_BANDS)[number];
}) {
  const style = TURBIDITY_STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${style.cls}`}
      title={style.hint}
      data-testid="turbidity-status"
    >
      {status}
    </span>
  );
}

interface TurbidityTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload?: { index?: number; status?: string | null; timestamp?: string };
  }>;
}

/** Tooltip for the relative-index chart: unit is always explicit. */
function TurbidityTooltip({ active, payload }: TurbidityTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point || typeof point.index !== "number") return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2 shadow-md">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
        Relative index (0–100)
      </p>
      <p className="text-sm font-extrabold text-slate-900">
        {point.index.toFixed(1)}
        <span className="text-[10px] font-semibold text-slate-400"> / 100</span>
      </p>
      {point.status ? (
        <p className="text-[10px] font-semibold text-slate-500">{point.status} · not NTU</p>
      ) : null}
      {point.timestamp ? (
        <p className="text-[10px] text-slate-400">
          {new Date(point.timestamp).toLocaleString()}
        </p>
      ) : null}
    </div>
  );
}

function CalibrationBadge({ status }: { status: string | null }) {
  if (status === "calibrated") {
    return (
      <span className="rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-px font-bold">
        calibrated
      </span>
    );
  }
  return (
    <span className="rounded-full bg-amber-100 text-amber-700 border border-amber-200 px-2 py-px font-bold">
      {status || "unknown"}
    </span>
  );
}

function ValueTile({
  label,
  icon,
  value,
  unit,
  diag,
  nullLabel,
  statusBadge,
  footnote,
}: {
  label: string;
  icon: React.ReactNode;
  value: number | null;
  unit: string;
  diag: SensorDiagnostics | null;
  nullLabel: string;
  statusBadge?: React.ReactNode;
  footnote?: string;
}) {
  const failed = diag?.valid === false || diag?.error != null;
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-2 text-slate-400">
        {icon}
        <span className="text-[11px] font-bold uppercase tracking-wider">{label}</span>
      </div>
      {value !== null ? (
        <p className="mt-1 text-xl font-extrabold text-slate-900 font-mono">
          {value}
          <span className="text-xs font-semibold text-slate-400">{unit}</span>
        </p>
      ) : (
        <p
          className={`mt-1 text-sm font-bold ${failed ? "text-red-600" : "text-amber-600"}`}
          title={
            failed
              ? "The device reported a sensor fault for this parameter."
              : "The device has this sensor but has not been calibrated — no honest value exists yet."
          }
        >
          {nullLabel}
        </p>
      )}
      {statusBadge ? <div className="mt-1.5">{statusBadge}</div> : null}
      <p className="text-[10px] text-slate-400 mt-1">
        {footnote
          ? footnote
          : value !== null
            ? diag?.calibration_status === "calibrated"
              ? "Calibrated reading"
              : "Reported by device"
            : failed
              ? "See diagnostics"
              : "Awaiting calibration"}
      </p>
    </div>
  );
}
