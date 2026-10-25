import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Clock,
  Cpu,
  Droplets,
  FlaskConical,
  Gauge,
  Info,
  Loader2,
  Radio,
  RefreshCw,
  ShieldAlert,
  Thermometer,
  Waves,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { authorityApi } from "../../lib/api";
import type {
  ApiError,
  IntendedUseCode,
  LiveAssessmentResponse,
  MonitoringStation,
  ProductReadingAssessment,
  StationReading,
} from "../../lib/api";
import { useLatestAnalysis } from "../../lib/useLatestAnalysis";
import { clearAuth, getToken } from "../../lib/auth";
import MlIndicator from "../../components/authority/MlIndicator";
import TelemetryStatusCard from "../../components/authority/TelemetryStatusCard";
import PublicPageQrCard from "../../components/authority/PublicPageQrCard";

const USES: { code: IntendedUseCode; label: string }[] = [
  { code: "drinking", label: "Drinking Water" },
  { code: "domestic", label: "Domestic Use" },
  { code: "irrigation", label: "Irrigation" },
  { code: "general", label: "General Non-Potable Use" },
  { code: "swimming", label: "Swimming / Recreation" },
  { code: "aquaculture", label: "Aquaculture" },
];

const PARAMETER_ICONS: Record<string, typeof Droplets> = {
  ph: FlaskConical,
  tds: Gauge,
  turbidity: Waves,
  temperature: Thermometer,
};

const STABILITY_STYLES: Record<string, string> = {
  stable: "border-emerald-200 bg-emerald-50 text-emerald-900",
  unstable: "border-orange-200 bg-orange-50 text-orange-900",
  collecting: "border-sky-200 bg-sky-50 text-sky-900",
  stabilizing: "border-sky-200 bg-sky-50 text-sky-900",
  waiting_for_data: "border-slate-200 bg-slate-50 text-slate-700",
  offline: "border-red-200 bg-red-50 text-red-900",
  sensor_error: "border-red-200 bg-red-50 text-red-900",
};

const OVERALL_STYLES: Record<
  string,
  { card: string; badge: string; icon: typeof CheckCircle2 }
> = {
  WITHIN_PROJECT_TARGETS: {
    card: "border-emerald-200 bg-emerald-50/50",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
    icon: CheckCircle2,
  },
  REVIEW_RECOMMENDED: {
    card: "border-amber-200 bg-amber-50/50",
    badge: "border-amber-200 bg-amber-50 text-amber-900",
    icon: AlertTriangle,
  },
  NOT_RECOMMENDED_BY_SCREENING: {
    card: "border-orange-200 bg-orange-50/50",
    badge: "border-orange-200 bg-orange-50 text-orange-900",
    icon: ShieldAlert,
  },
  INCONCLUSIVE: {
    card: "border-slate-300 bg-slate-50",
    badge: "border-slate-300 bg-slate-100 text-slate-700",
    icon: Info,
  },
};

function parameterStyle(status: string): string {
  switch (status) {
    case "within_range":
    case "no_restriction":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "below_project_target":
    case "above_acceptable":
    case "slight_restriction":
      return "border-amber-200 bg-amber-50 text-amber-900";
    case "above_permissible":
    case "severe_restriction":
    case "below_reference":
    case "above_reference":
    case "invalid":
      return "border-orange-200 bg-orange-50 text-orange-900";
    case "not_comparable":
    case "not_measured":
    case "informational":
      return "border-slate-200 bg-slate-50 text-slate-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "No reading yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function ageSeconds(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.now() - new Date(value).getTime();
  return Number.isNaN(ms) ? null : Math.max(Math.floor(ms / 1000), 0);
}

function SensorCard({
  reading,
  calibration,
  timestamp,
}: {
  reading: ProductReadingAssessment;
  calibration: string | undefined;
  timestamp: string | null;
}) {
  const Icon = PARAMETER_ICONS[reading.parameter] ?? Droplets;
  const age = ageSeconds(timestamp);
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-slate-600">
          <Icon className="h-4.5 w-4.5" aria-hidden="true" />
          <h3 className="text-sm font-bold text-slate-800">{reading.label}</h3>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${parameterStyle(reading.status)}`}
        >
          {reading.status_label}
        </span>
      </div>

      <p className="mt-4 flex flex-wrap items-baseline gap-1.5">
        <span className="text-3xl font-extrabold tracking-tight text-slate-900">
          {reading.value === null ? "—" : Number(reading.value.toFixed(2))}
        </span>
        <span className="text-xs font-semibold text-slate-500">
          {reading.value === null ? "No value" : reading.unit || (reading.parameter === "ph" ? "pH" : "")}
        </span>
      </p>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
        {reading.reference}
      </p>
      {reading.note && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">{reading.note}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-2 text-[10px] font-semibold text-slate-500">
        <span className="inline-flex items-center gap-1">
          <Clock className="h-3 w-3" aria-hidden="true" />
          {age === null ? "No timestamp" : `${age} s ago`}
        </span>
        <span className="inline-flex items-center gap-1">
          <Cpu className="h-3 w-3" aria-hidden="true" />
          {calibration ? calibration.replace(/_/g, " ") : "calibration unknown"}
        </span>
      </div>
    </div>
  );
}

function StabilityPanel({ data }: { data: LiveAssessmentResponse }) {
  const stability = data.stability;
  const style = STABILITY_STYLES[stability.status] ?? STABILITY_STYLES.waiting_for_data;
  return (
    <section className={`rounded-2xl border p-5 shadow-xs ${style}`} aria-labelledby="stability-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider opacity-70">
            Sensor stability
          </p>
          <h2 id="stability-heading" className="mt-0.5 text-lg font-extrabold">
            {stability.status_label}
          </h2>
          <p className="mt-1 text-xs leading-relaxed opacity-90">{stability.message}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-extrabold">{stability.valid_samples}/{stability.required_samples}</p>
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-70">valid samples</p>
        </div>
      </div>

      <div className="mt-4">
        <div className="h-2 overflow-hidden rounded-full bg-white/70">
          <div
            className={`h-full rounded-full ${
              stability.status === "stable"
                ? "bg-emerald-500"
                : stability.status === "unstable" || stability.status === "offline" || stability.status === "sensor_error"
                  ? "bg-orange-500"
                  : "bg-sky-500"
            }`}
            style={{ width: `${Math.max(2, stability.progress)}%` }}
          />
        </div>
        <div className="mt-1.5 flex flex-wrap justify-between gap-2 text-[10px] font-semibold opacity-80">
          <span>
            Window: {stability.valid_samples} samples over {stability.span_seconds.toFixed(1)} s
            {" "}(need {stability.required_samples} / {stability.required_span_seconds} s)
          </span>
          <span>Firmware publishes every {stability.firmware_publish_interval_seconds} s</span>
        </div>
      </div>

      {Object.keys(stability.per_parameter).length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {Object.entries(stability.per_parameter).map(([key, item]) => (
            <div key={key} className="rounded-xl border border-white/70 bg-white/70 p-2.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                {item.label}
              </p>
              <p className="mt-0.5 text-xs font-bold text-slate-800">
                Δ {item.range} <span className="font-medium text-slate-500">/ ±{item.tolerance}</span>
              </p>
              <p
                className={`text-[10px] font-bold ${
                  item.stable ? "text-emerald-700" : "text-orange-700"
                }`}
              >
                {item.stable ? "Within tolerance" : "Outside tolerance"}
              </p>
            </div>
          ))}
        </div>
      )}

      {stability.sensor_errors.length > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-xs font-semibold text-red-800">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {stability.sensor_errors.join("; ")}
        </p>
      )}
    </section>
  );
}

function AssessmentPanel({ data }: { data: LiveAssessmentResponse }) {
  const { assessment } = data;
  const overall = assessment.overall;
  const style = OVERALL_STYLES[overall.status] ?? OVERALL_STYLES.INCONCLUSIVE;
  const StatusIcon = style.icon;
  const stability = data.stability;

  return (
    <section
      className={`rounded-3xl border p-6 shadow-sm ${style.card}`}
      aria-labelledby="live-assessment-heading"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className={`rounded-xl border bg-white p-2.5 ${style.badge}`}>
            <StatusIcon className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              {assessment.intended_use_label} assessment
            </p>
            <h2
              id="live-assessment-heading"
              className="mt-0.5 text-xl font-extrabold text-slate-900 sm:text-2xl"
            >
              {overall.label}
            </h2>
            <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-700">
              {overall.summary}
            </p>
          </div>
        </div>
        <span className={`inline-flex w-fit items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-bold ${style.badge}`}>
          {stability.stable ? "Stable reading" : "Not stable"}
        </span>
      </div>

      {!stability.stable && (
        <div className="mt-4 rounded-xl border border-slate-300 bg-white/80 p-4 text-sm text-slate-700">
          <p className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <strong>Waiting for stable readings.</strong> {stability.message} The
              assessment stays inconclusive until the rolling window is stable.
            </span>
          </p>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Object.values(assessment.readings).map((reading) => (
          <div key={reading.parameter} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-bold text-slate-800">{reading.label}</p>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${parameterStyle(reading.status)}`}>
                {reading.status_label}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-600">
              {reading.value === null
                ? "No measurement"
                : `${reading.value} ${reading.unit}`.trim()}
              <span className="text-slate-400"> · {reading.reference}</span>
            </p>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-bold text-slate-900">Why did I get this result?</h3>
        {assessment.overall.reason_details && assessment.overall.reason_details.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {assessment.overall.reason_details.map((detail, index) => (
              <li key={`${detail.parameter}-${index}`} className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs font-bold text-slate-800">
                  {detail.label}
                  {detail.value !== null ? ` · ${detail.value} ${detail.unit}` : ""}
                  <span className="ml-2 font-semibold text-slate-500">{detail.status_label}</span>
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-700">{detail.reason}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Reference: {detail.reference}</p>
                {detail.calibration_limitation && (
                  <p className="mt-0.5 text-[11px] text-amber-700">
                    Calibration/data quality: {detail.calibration_limitation}
                  </p>
                )}
                <p className="mt-0.5 text-[11px] font-semibold text-cyan-800">
                  Next step: {detail.next_step}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-slate-600">
            No parameter-level concern was recorded for this screening.
          </p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-bold text-slate-900">Recommended next action</h3>
          <ul className="mt-2 space-y-1.5">
            {assessment.next_steps.map((step) => (
              <li key={step} className="flex items-start gap-2 text-xs text-slate-700">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-cyan-500" />
                {step}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-bold text-slate-900">
            Calibration and data-quality limitations
          </h3>
          <p className="mt-1 text-xs text-slate-600">
            Calibration status:{" "}
            <strong className="text-slate-800">
              {assessment.data_quality.calibration_status}
            </strong>{" "}
            · stability and calibration are assessed separately.
          </p>
          <ul className="mt-2 space-y-1">
            {[...assessment.data_quality.errors, ...assessment.data_quality.warnings]
              .slice(0, 6)
              .map((warning) => (
                <li key={warning} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" aria-hidden="true" />
                  {warning}
                </li>
              ))}
          </ul>
          <p className="mt-2 text-[10px] text-slate-400">
            Test ID: {data.test_id ?? "Pending a stable reading"} · Criteria{" "}
            {data.criteria_version}
          </p>
          <p className="text-[10px] text-slate-400">
            Reading timestamp: {formatTime(data.last_received)}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-slate-300 bg-white/80 p-4 text-xs leading-relaxed text-slate-700">
        <strong>Not a certification.</strong> {assessment.suitability.limitations.join(" ")}
      </div>
    </section>
  );
}

const TREND_PARAMETERS = [
  { key: "ph", label: "pH", color: "#8b5cf6" },
  { key: "tds", label: "TDS (mg/L)", color: "#6366f1" },
  { key: "turbidity", label: "Turbidity", color: "#06b6d4" },
  { key: "temperature", label: "Temperature (°C)", color: "#f59e0b" },
] as const;

type TrendKey = (typeof TREND_PARAMETERS)[number]["key"];

function StationHistory({ stationCode }: { stationCode: string | null }) {
  const [readings, setReadings] = useState<StationReading[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parameter, setParameter] = useState<TrendKey>("ph");

  useEffect(() => {
    if (!stationCode) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    authorityApi
      .getStationReadings(stationCode, token, 40)
      .then((rows) => {
        if (cancelled) return;
        setReadings(rows);
        setError(null);
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setError(err.detail || "Unable to load reading history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stationCode]);

  if (!stationCode) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Select a station to view history.
      </div>
    );
  }

  const ordered = [...readings].reverse();
  const latestUnit = readings[0]?.turbidity_unit ?? null;
  const valueOf = (row: StationReading): number | null => {
    if (parameter === "ph") return row.pH;
    if (parameter === "tds") return row.tds;
    if (parameter === "temperature") return row.temperature;
    return row.turbidity;
  };
  const chartRows = ordered.filter((row) => {
    if (parameter === "turbidity") {
      return row.turbidity !== null && row.turbidity_unit === latestUnit;
    }
    return valueOf(row) !== null;
  });
  const chartData = chartRows.map((row) => ({
    time: new Date(row.timestamp).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    value: valueOf(row),
  }));
  const unit =
    parameter === "turbidity"
      ? latestUnit === "ntu"
        ? "NTU"
        : latestUnit === "relative_index_0_100"
          ? "relative index (not NTU)"
          : "unit unknown"
      : parameter === "tds"
        ? "mg/L"
        : parameter === "temperature"
          ? "°C"
          : "";

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
      <div className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-900">Historical trend and recent readings</h2>
          <p className="text-xs text-slate-500">
            Real stored MQTT readings for this station. Turbidity is never mixed across units.
          </p>
        </div>
        <div className="flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1">
          {TREND_PARAMETERS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setParameter(item.key)}
              className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold ${
                parameter === item.key
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading reading history…
        </p>
      ) : error ? (
        <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          {error}
        </p>
      ) : chartData.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No comparable readings yet for this parameter.
        </p>
      ) : (
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }}
                formatter={(value) => [`${value} ${unit}`, parameter.toUpperCase()]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={TREND_PARAMETERS.find((item) => item.key === parameter)?.color ?? "#0891b2"}
                strokeWidth={2}
                dot={{ r: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-right text-[10px] text-slate-400">
            Unit: {unit || "—"} · showing last {chartData.length} readings
          </p>
        </div>
      )}

      <div className="mt-4 max-h-64 overflow-auto rounded-xl border border-slate-100">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2 font-bold">Timestamp</th>
              <th className="px-3 py-2 font-bold">pH</th>
              <th className="px-3 py-2 font-bold">TDS</th>
              <th className="px-3 py-2 font-bold">Turbidity</th>
              <th className="px-3 py-2 font-bold">Temp</th>
              <th className="px-3 py-2 font-bold">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-600">
            {readings.slice(0, 12).map((row) => (
              <tr key={row.id}>
                <td className="whitespace-nowrap px-3 py-1.5">{formatTime(row.timestamp)}</td>
                <td className="px-3 py-1.5">{row.pH ?? "—"}</td>
                <td className="px-3 py-1.5">{row.tds !== null ? `${row.tds} mg/L` : "—"}</td>
                <td className="px-3 py-1.5">
                  {row.turbidity === null
                    ? "—"
                    : `${row.turbidity} ${
                        row.turbidity_unit === "ntu"
                          ? "NTU"
                          : row.turbidity_unit === "relative_index_0_100"
                            ? "index"
                            : "(unit unknown)"
                      }`}
                </td>
                <td className="px-3 py-1.5">{row.temperature !== null ? `${row.temperature} °C` : "—"}</td>
                <td className="px-3 py-1.5">{row.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LiveMonitoringPanel({ station }: { station: MonitoringStation }) {
  const [use, setUse] = useState<IntendedUseCode>("drinking");
  const [aquacultureContext, setAquacultureContext] = useState("");
  const [data, setData] = useState<LiveAssessmentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<number | null>(null);
  const latest = useLatestAnalysis(station.station_code);
  const latestML = latest.status === "success" ? latest.data : null;

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setError("Sign in with an authority account to view live monitoring.");
      return;
    }
    try {
      const result = await authorityApi.getLiveAssessment(
        station.station_code,
        token,
        use,
        use === "aquaculture" && aquacultureContext ? aquacultureContext : undefined
      );
      setData(result);
      setError(null);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        setError("Your session expired. Sign in again.");
      } else if (apiError.statusCode === 403) {
        setError("Your account is not authorized to view live monitoring.");
      } else if (apiError.statusCode === 404) {
        setError(apiError.detail || "This station has no readings yet.");
      } else {
        setError(apiError.detail || "Unable to load live monitoring data.");
      }
    } finally {
      setRefreshing(false);
    }
  }, [station.station_code, use, aquacultureContext]);

  useEffect(() => {
    const initial = window.setTimeout(load, 0);
    intervalRef.current = window.setInterval(load, 5000);
    return () => {
      window.clearTimeout(initial);
      if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    };
  }, [load]);

  const selectUse = (next: IntendedUseCode) => {
    setUse(next);
    setData(null);
    setRefreshing(true);
  };

  const refresh = () => {
    setRefreshing(true);
    load();
  };

  const headerTimestamp = data?.last_received ?? data?.latest?.timestamp ?? null;
  const connection = data?.connection ?? "no_data";
  const connectionLabel = data?.connection_label ?? "Connecting";

  const connectionStyle =
    connection === "connected"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : connection === "connecting"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : connection === "error"
          ? "border-red-200 bg-red-50 text-red-800"
          : connection === "offline"
            ? "border-red-200 bg-red-50 text-red-800"
            : "border-slate-200 bg-slate-50 text-slate-700";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-[11px] font-bold text-cyan-800">
              <Radio className={`h-3.5 w-3.5 ${data?.live ? "animate-pulse" : ""}`} aria-hidden="true" />
              {data?.live ? "LIVE" : "POLLING"} · updates every {data?.poll_interval_seconds ?? 5} s
            </div>
            <h2 className="mt-2 text-xl font-bold tracking-tight text-slate-900">
              Station telemetry
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {station.station_name} ·{" "}
              <span className="font-mono text-xs font-bold text-slate-700">{station.station_code}</span>
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Device: {data?.device_id ?? "No device yet"} · Source:{" "}
              {data?.water_source_name ?? station.water_source?.name ?? "Unknown"}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2 lg:text-right">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Connection
              </p>
              <span className={`mt-0.5 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${connectionStyle}`}>
                {connection === "connected" ? (
                  <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
                ) : connection === "connecting" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {connectionLabel}
              </span>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Last received
              </p>
              <p className="mt-1 font-semibold text-slate-700">{formatTime(headerTimestamp)}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Water source
              </p>
              <p className="mt-1 font-semibold text-slate-700">
                {data?.water_source_name ?? station.water_source?.name ?? "Unknown"}
              </p>
            </div>
            <div className="flex items-start gap-2 lg:justify-end">
              <button
                type="button"
                onClick={refresh}
                disabled={refreshing}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white py-16 text-sm text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-600" aria-hidden="true" />
          Waiting for sensor data…
        </div>
      )}

      {data && (
        <>
          <StabilityPanel data={data} />

          <section aria-labelledby="sensor-heading">
            <div className="mb-2 flex items-end justify-between">
              <div>
                <h2 id="sensor-heading" className="text-lg font-bold text-slate-900">
                  Four sensor readings
                </h2>
                <p className="text-xs text-slate-500">
                  Values are from the latest stored reading. Stability does not imply calibration.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {Object.values(data.assessment.readings).map((reading) => (
                <SensorCard
                  key={reading.parameter}
                  reading={reading}
                  calibration={data.stability.calibration[reading.parameter]}
                  timestamp={headerTimestamp}
                />
              ))}
            </div>
          </section>

          {/* Intended use selector */}
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <h2 className="text-sm font-bold text-slate-800">Assess for intended use</h2>
            <p className="text-xs text-slate-500">
              Changing the use reruns the shared assessment on the current stable readings.
            </p>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5" role="group" aria-label="Intended use">
              {USES.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => selectUse(item.code)}
                  aria-pressed={use === item.code}
                  className={`rounded-xl border-2 px-3 py-2.5 text-left text-xs font-bold transition-colors ${
                    use === item.code
                      ? "border-cyan-500 bg-cyan-50 text-cyan-900"
                      : "border-slate-100 text-slate-600 hover:border-cyan-300 hover:bg-cyan-50/50"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {use === "aquaculture" && (
              <label className="mt-3 block text-xs font-semibold text-slate-600">
                Species / farming context (optional)
                <input
                  type="text"
                  value={aquacultureContext}
                  onChange={(event) => setAquacultureContext(event.target.value)}
                  placeholder="e.g. tilapia nursery pond"
                  maxLength={200}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal text-slate-800 focus:border-cyan-500 focus:outline-none"
                />
                <span className="mt-1 block text-[10px] font-normal text-slate-400">
                  No species-specific criteria are configured; this context is recorded with the assessment only.
                </span>
              </label>
            )}
          </section>

          {refreshing && !data ? (
            <div className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white py-12 text-sm text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin text-cyan-600" aria-hidden="true" />
              Running {use.replace("_", " ")} assessment…
            </div>
          ) : (
            <AssessmentPanel data={data} />
          )}

          <StationHistory stationCode={station.station_code} />

          {/* ML is context only; it is not the rule-based assessment above. */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Brain className="h-4.5 w-4.5 text-cyan-600" aria-hidden="true" />
                <h2 className="text-sm font-bold text-slate-900">ML analysis — latest reading</h2>
              </div>
              <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-700">
                Context only · not this screening
              </span>
            </div>
            <div className="mt-4">
              {latest.status === "loading" && (
                <p className="animate-pulse text-sm text-slate-500">Loading ML analysis…</p>
              )}
              {latest.status === "success" && latestML && (
                <>
                  <p className="mb-3 text-[11px] text-slate-500">
                    Reading #{latestML.reading_id} · {new Date(latestML.timestamp).toLocaleString()}
                  </p>
                  <MlIndicator
                    anomalyLabel={latestML.ml.anomaly_label}
                    anomalyScore={latestML.ml.anomaly_score}
                    qualityLabel={latestML.ml.water_quality_label}
                  />
                </>
              )}
              {(latest.status === "unavailable" || latest.status === "idle") && (
                <p className="text-sm text-slate-500">
                  {latest.message || "Analysis unavailable — no ML result for this station yet."}{" "}
                  No default classification is assumed.
                </p>
              )}
              {latest.status === "unauthorized" && (
                <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                  {latest.message || "AI analysis is restricted to authority accounts."}
                </p>
              )}
              {latest.status === "error" && (
                <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                  {latest.message || "Failed to load ML analysis."}
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <TelemetryStatusCard stationCode={station.station_code} />
            <PublicPageQrCard stationCode={station.station_code} />
          </div>
        </>
      )}
    </div>
  );
}

export default function LiveMonitoring() {
  const [stations, setStations] = useState<MonitoringStation[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      const timer = window.setTimeout(() => {
        setError("Sign in with an authority account to view live monitoring.");
        setLoading(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }
    let cancelled = false;
    authorityApi
      .getAllStations(token)
      .then((data) => {
        if (cancelled) return;
        setStations(data);
        setSelectedCode((current) => current ?? data[0]?.station_code ?? null);
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setError(err.detail || "Unable to load monitoring stations.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-sm text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin text-cyan-600" aria-hidden="true" />
        Loading monitoring stations…
      </div>
    );
  }

  if (error || stations.length === 0) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-amber-600" aria-hidden="true" />
        <h1 className="mt-2 text-lg font-bold text-slate-900">Live monitoring unavailable</h1>
        <p className="mt-1 text-sm text-slate-700">
          {error || "No monitoring stations are configured. Seed the demo data first."}
        </p>
      </div>
    );
  }

  const station = stations.find((item) => item.station_code === selectedCode) ?? stations[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Live Water Monitoring
          </h1>
          <p className="text-xs text-slate-500">
            Real ESP32/MQTT telemetry, rolling-window stability and the shared four-sensor assessment.
          </p>
        </div>
        <label className="text-xs font-bold text-slate-600">
          Station
          <select
            value={station.station_code}
            onChange={(event) => setSelectedCode(event.target.value)}
            className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-800 shadow-xs focus:border-cyan-500 focus:outline-none"
          >
            {stations.map((item) => (
              <option key={item.id} value={item.station_code}>
                {item.station_code} — {item.station_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <LiveMonitoringPanel key={station.station_code} station={station} />
    </div>
  );
}
