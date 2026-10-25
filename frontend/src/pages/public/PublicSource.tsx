import { useParams, Link } from "react-router-dom";
import { useState, useEffect, useMemo } from "react";
import {
  ArrowLeft,
  AlertTriangle,
  Loader,
  Droplets,
  Thermometer,
  FlaskConical,
  Radio,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type {
  MonitoringStation,
  ApiError,
  PublicLatestReading,
  PublicReadingHistoryRow,
} from "../../lib/api";
import { publicApi } from "../../lib/api";
import WaterSuitabilitySection from "../../components/authority/WaterSuitabilitySection";

type LinkState = "online" | "stale" | "offline";

function linkState(timestamp: string | null): LinkState {
  if (!timestamp) return "offline";
  const ageSeconds = (Date.now() - new Date(timestamp).getTime()) / 1000;
  if (ageSeconds <= 15) return "online";
  if (ageSeconds <= 300) return "stale";
  return "offline";
}

function formatValue(
  value: number | null,
  unit = "",
  unavailable = "Not calibrated"
): string {
  if (value === null || value === undefined) return unavailable;
  return `${Number.isInteger(value) ? value : value.toFixed(2)}${unit ? ` ${unit}` : ""}`;
}

function turbidityUnitLabel(unit: string | null): string {
  if (unit === "relative_index_0_100") return "provisional index 0–100 (not NTU)";
  if (unit === "ntu") return "NTU";
  return "unit not recorded";
}

export default function PublicSource() {
  const { stationId } = useParams<{ stationId: string }>();
  const [station, setStation] = useState<MonitoringStation | null>(null);
  const [latest, setLatest] = useState<PublicLatestReading | null>(null);
  const [noReadings, setNoReadings] = useState(false);
  const [history, setHistory] = useState<PublicReadingHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stationId) return;

    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const data = await publicApi.getStationByCode(stationId);
        if (cancelled) return;
        setStation(data);
        setError(null);

        try {
          const latestData = await publicApi.getLatestReading(stationId);
          if (!cancelled) {
            // Guard against a malformed/legacy payload: the page must not crash
            // on an unexpected response shape.
            if (latestData && typeof latestData.timestamp === "string") {
              setLatest(latestData);
              setNoReadings(false);
            } else {
              setLatest(null);
              setNoReadings(true);
            }
          }
        } catch (err) {
          if (!cancelled && (err as ApiError).statusCode === 404) {
            setLatest(null);
            setNoReadings(true);
          }
        }

        try {
          const rows = await publicApi.getReadingHistory(stationId, 50);
          if (!cancelled) setHistory(Array.isArray(rows) ? rows : []);
        } catch {
          if (!cancelled) setHistory([]);
        }
      } catch (err) {
        if (cancelled) return;
        const apiError = err as ApiError;
        setError(apiError.detail || "Failed to load station data");
        setStation(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [stationId]);

  const state: LinkState = linkState(latest?.timestamp ?? null);

  const trend = useMemo(
    () =>
      [...history]
        .reverse()
        .filter((row) => row.temperature !== null)
        .map((row) => ({
          time: new Date(row.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          temperature: row.temperature,
        })),
    [history]
  );

  if (loading) {
    return (
      <div className="py-12 px-4 text-center">
        <Loader className="h-8 w-8 animate-spin mx-auto text-cyan-600 mb-4" />
        <p className="text-slate-600">Loading station data...</p>
      </div>
    );
  }

  if (error || !station) {
    return (
      <div className="py-12 px-4 text-center">
        <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-slate-900">Station not found</h2>
        <p className="text-sm text-slate-500 mt-2">{error || "This station could not be found."}</p>
        <Link to="/public" className="text-cyan-600 mt-4 inline-block hover:underline">
          Return Home
        </Link>
      </div>
    );
  }

  const getWarningStyles = (warning: string) => {
    switch (warning) {
      case "CRITICAL":
        return "bg-red-50 text-red-700 border-red-200";
      case "WARNING":
      case "CAUTION":
        return "bg-amber-50 text-amber-700 border-amber-200";
      default:
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
    }
  };

  const stateStyles: Record<LinkState, string> = {
    online: "bg-emerald-100 text-emerald-700 border-emerald-200",
    stale: "bg-amber-100 text-amber-700 border-amber-200",
    offline: "bg-slate-100 text-slate-500 border-slate-200",
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <Link to="/public" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" />
        <span>Back to Home</span>
      </Link>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-500">{station.station_code}</p>
              <h1 className="text-2xl font-bold text-slate-900 mt-1">{station.station_name}</h1>
              <p className="text-slate-500 mt-1">{station.location}</p>
              <p className="text-xs text-slate-400 mt-2">{station.zone}</p>
            </div>
            <div className={`px-4 py-2 rounded-xl border font-bold flex items-center gap-2 ${getWarningStyles(station.public_warning)}`}>
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-current"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-current"></span>
              </span>
              {station.public_warning}
            </div>
          </div>

          <div className="mt-6 p-4 bg-cyan-50 border border-cyan-200 rounded-xl">
            <p className="text-sm text-cyan-900 font-medium">{station.public_message}</p>
          </div>

          {/* Water source */}
          <div className="mt-8">
            <h2 className="text-sm font-semibold text-slate-700 mb-3">Water Source</h2>
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <p className="text-sm text-slate-600">
                <span className="font-semibold">{station.water_source.name}</span>
                <span className="text-slate-500 ml-2">({station.water_source.source_type})</span>
              </p>
              {station.water_source.description && (
                <p className="text-sm text-slate-500 mt-2">{station.water_source.description}</p>
              )}
            </div>
          </div>

          {/* Latest measurements */}
          <div className="mt-8">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Droplets className="h-4 w-4 text-cyan-600" /> Latest Measurements
              </h2>
              <span
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${stateStyles[state]}`}
                data-testid="public-link-state"
              >
                <Radio className="h-3 w-3" />
                {state === "online" ? "Live" : state === "stale" ? "Stale data" : "Offline"}
              </span>
            </div>

            {noReadings || !latest ? (
              <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                No telemetry has been received from this station yet. Values will appear here
                automatically once the device reports.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <ValueTile label="pH" value={formatValue(latest.pH)} hint={latest.pH === null ? "Not calibrated yet" : ""} />
                  <ValueTile
                    label="Total dissolved solids"
                    value={formatValue(latest.tds, "mg/L")}
                    hint={latest.tds === null ? "Not calibrated yet" : ""}
                  />
                  <ValueTile
                    label="Turbidity"
                    value={formatValue(latest.turbidity, "", "Not available")}
                    hint={turbidityUnitLabel(latest.turbidity_unit)}
                  />
                  <ValueTile
                    label="Temperature"
                    value={formatValue(latest.temperature, "°C", "Sensor unavailable")}
                    hint="DS18B20"
                  />
                </div>
                <p className="mt-2 text-[11px] text-slate-400">
                  Last reading: {new Date(latest.timestamp).toLocaleString()} · source:{" "}
                  {latest.source === "esp32" ? "physical station hardware" : "simulated demonstration data"}
                </p>
              </>
            )}
          </div>

          {/* Temperature trend */}
          {trend.length >= 2 && (
            <div className="mt-8">
              <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <Thermometer className="h-4 w-4 text-cyan-600" /> Recent temperature trend (°C)
              </h2>
              <div className="h-48 rounded-xl border border-slate-100 bg-slate-50 p-3" data-testid="public-trend">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" width={34} />
                    <Tooltip />
                    <Line type="monotone" dataKey="temperature" stroke="#0891b2" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Recent readings table */}
          {history.length > 0 && (
            <div className="mt-8">
              <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-cyan-600" /> Recent readings
              </h2>
              <div className="overflow-x-auto rounded-xl border border-slate-100">
                <table className="w-full min-w-[420px] text-left text-[11px]">
                  <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400">
                    <tr>
                      <th className="px-3 py-2 font-bold">Time</th>
                      <th className="px-3 py-2 font-bold">pH</th>
                      <th className="px-3 py-2 font-bold">TDS</th>
                      <th className="px-3 py-2 font-bold">Turbidity</th>
                      <th className="px-3 py-2 font-bold">Temp (°C)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.slice(0, 10).map((row) => (
                      <tr key={row.id} className="border-t border-slate-50 text-slate-600">
                        <td className="px-3 py-1.5">{new Date(row.timestamp).toLocaleTimeString()}</td>
                        <td className="px-3 py-1.5">{formatValue(row.pH)}</td>
                        <td className="px-3 py-1.5">{formatValue(row.tds, "mg/L")}</td>
                        <td className="px-3 py-1.5">
                          {formatValue(row.turbidity)}
                          {row.turbidity_unit === "relative_index_0_100" && (
                            <span className="ml-1 text-[10px] text-slate-400">(index)</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">{formatValue(row.temperature, "", "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Location */}
          <div className="mt-8 grid grid-cols-2 gap-4">
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <p className="text-xs font-semibold text-slate-500 uppercase">Latitude</p>
              <p className="text-lg font-bold text-slate-900 mt-1">{station.latitude.toFixed(4)}</p>
            </div>
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <p className="text-xs font-semibold text-slate-500 uppercase">Longitude</p>
              <p className="text-lg font-bold text-slate-900 mt-1">{station.longitude.toFixed(4)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Standards-based suitability (public endpoint, no login) */}
      <WaterSuitabilitySection stationCode={station.station_code} mode="public" />

      <div className="text-xs text-slate-500 text-center space-y-1">
        <p>
          Information is provided for awareness. Measured values are raw sensor readings; pH/TDS
          require laboratory calibration, and turbidity may be a provisional relative index rather
          than NTU.
        </p>
        <p>Assessments are rule-based screenings against published standards — not laboratory certificates.</p>
      </div>
    </div>
  );
}

function ValueTile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-0.5 text-lg font-extrabold text-slate-900">{value}</p>
      {hint && <p className="text-[10px] text-slate-400 mt-0.5">{hint}</p>}
    </div>
  );
}
