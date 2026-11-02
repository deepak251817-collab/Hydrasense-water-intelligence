import { useEffect, useState } from "react";
import { waterUseOptions } from "../../data/mockData";
import type { WaterUseCategory } from "../../data/mockData";
import WaterUseCard from "../../components/public/WaterUseCard";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  MapPin,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import type {
  ApiError,
  PublicStation,
  WaterSuitabilityAssessment,
} from "../../lib/api";
import { publicApi } from "../../lib/api";

/** Maps the UI use cards to the backend's supported screening profiles. */
const USE_TO_API: Record<WaterUseCategory["id"], string> = {
  drinking: "drinking",
  domestic: "domestic",
  irrigation: "irrigation",
};

const RESULT_STYLES: Record<string, string> = {
  preliminary_suitable: "bg-emerald-50 border-emerald-200 text-emerald-900",
  treatment_required: "bg-amber-50 border-amber-200 text-amber-900",
  outside_limits: "bg-red-50 border-red-200 text-red-900",
  lab_confirmation_required: "bg-cyan-50 border-cyan-200 text-cyan-900",
  insufficient_data: "bg-slate-50 border-slate-200 text-slate-800",
};

const PARAMETER_STYLES: Record<string, string> = {
  within_acceptable: "bg-emerald-100 text-emerald-700 border-emerald-200",
  within_permissible: "bg-amber-100 text-amber-700 border-amber-200",
  outside_limits: "bg-red-100 text-red-700 border-red-200",
  not_measured: "bg-slate-100 text-slate-600 border-slate-200",
  not_comparable: "bg-amber-50 text-amber-700 border-amber-200",
};

function warningStyles(warning: string): string {
  switch (warning) {
    case "CRITICAL":
      return "bg-red-100 text-red-700";
    case "WARNING":
    case "CAUTION":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-emerald-100 text-emerald-700";
  }
}

function scoreLabel(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "not measured";
  return `${Number.isInteger(value) ? value : value.toFixed(2)}${unit ? ` ${unit}` : ""}`;
}

export default function WaterCheck() {
  const [stations, setStations] = useState<PublicStation[]>([]);
  const [stationCode, setStationCode] = useState<string>("");
  const [selectedUse, setSelectedUse] = useState<WaterUseCategory["id"]>("drinking");
  const [loadingStations, setLoadingStations] = useState(true);
  const [loadingResult, setLoadingResult] = useState(false);
  const [stationError, setStationError] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [assessments, setAssessments] = useState<WaterSuitabilityAssessment[] | null>(
    null
  );
  const [requestedUse, setRequestedUse] = useState<WaterUseCategory["id"] | null>(null);
  const [rulesetVersion, setRulesetVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await publicApi.getStations();
        if (cancelled) return;
        setStations(rows);
        setStationCode((current) => current || rows[0]?.station_code || "");
      } catch (err) {
        if (cancelled) return;
        setStationError((err as ApiError).detail || "Failed to load stations.");
      } finally {
        if (!cancelled) setLoadingStations(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedStation = stations.find((station) => station.station_code === stationCode);
  const selectedUseOption =
    waterUseOptions.find((use) => use.id === selectedUse) || waterUseOptions[0];

  const handleStartCheck = async () => {
    if (!stationCode) return;
    setLoadingResult(true);
    setResultError(null);
    setAssessments(null);
    try {
      const response = await publicApi.getSuitability(stationCode);
      setAssessments(response.assessments);
      setRulesetVersion(response.ruleset_version);
      setRequestedUse(selectedUse);
    } catch (err) {
      setResultError(
        (err as ApiError).detail || "The screening assessment is unavailable."
      );
    } finally {
      setLoadingResult(false);
    }
  };

  const activeAssessment =
    assessments?.find((item) => item.use === USE_TO_API[requestedUse ?? selectedUse]) ??
    null;
  const resultStyles = activeAssessment
    ? RESULT_STYLES[activeAssessment.result] ?? RESULT_STYLES.insufficient_data
    : RESULT_STYLES.insufficient_data;

  return (
    <div className="mx-auto max-w-5xl py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Page header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-cyan-100 px-3 py-1 text-xs font-bold text-cyan-800">
          <ShieldCheck className="h-3.5 w-3.5 text-cyan-700" />
          <span>Intended-Use Screening</span>
        </div>
        <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
          Check Water Suitability
        </h1>
        <p className="mt-1 text-sm text-slate-500 max-w-2xl leading-relaxed">
          Select a monitored station and what you intend to use the water for. The
          result comes from the central backend screening engine using only the four
          measured parameters: pH, TDS, temperature and the relative turbidity index.
        </p>
      </div>

      {/* Honest scope notice */}
      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-xs text-amber-950 flex items-start gap-3">
        <Info className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-bold text-amber-900">Preliminary screening, not a certification</p>
          <p className="leading-relaxed text-amber-800">
            The turbidity sensor reports a relative 0–100 index, not calibrated NTU, so
            NTU-based turbidity limits cannot be applied. Microbiological, heavy-metal and
            other chemical hazards are not measured by this hardware. Every result states
            which required tests are still missing.
          </p>
        </div>
      </div>

      {/* Step 1: station */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-cyan-700">
              Step 1
            </span>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight mt-0.5">
              Select monitored station
            </h2>
          </div>
          {!loadingStations && stations.length > 0 && (
            <span className="text-xs font-medium text-slate-400">
              {stations.length} public station{stations.length === 1 ? "" : "s"}
            </span>
          )}
        </div>

        {loadingStations ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
            Loading stations…
          </div>
        ) : stationError ? (
          <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{stationError}</span>
          </div>
        ) : stations.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
            No public stations are available yet. Values appear after a station is
            registered and a device reports readings.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stations.map((station) => (
              <button
                key={station.station_code}
                type="button"
                onClick={() => {
                  setStationCode(station.station_code);
                  setAssessments(null);
                  setResultError(null);
                }}
                className={`flex items-start justify-between rounded-xl p-3.5 border text-left transition-all ${
                  stationCode === station.station_code
                    ? "border-cyan-600 bg-cyan-50/40 ring-2 ring-cyan-600/20"
                    : "border-slate-200 hover:border-slate-300 bg-white"
                }`}
              >
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    {station.water_source.source_type}
                  </span>
                  <h4 className="text-sm font-bold text-slate-900 mt-0.5">
                    {station.station_name}
                  </h4>
                  <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                    <MapPin className="h-3 w-3" />
                    <span>{station.location}</span>
                  </div>
                  <p className="mt-1 text-[10px] font-mono text-slate-400">
                    {station.station_code}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${warningStyles(station.public_warning)}`}
                >
                  {station.public_warning}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Step 2: intended use */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-cyan-700">
              Step 2
            </span>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight mt-0.5">
              What will you use this water for?
            </h2>
          </div>
          <span className="text-xs font-semibold text-slate-400">Choose one primary use</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {waterUseOptions.map((useOption) => (
            <WaterUseCard
              key={useOption.id}
              useOption={useOption}
              isSelected={selectedUse === useOption.id}
              onSelect={(id) => {
                setSelectedUse(id);
                setAssessments(null);
                setResultError(null);
              }}
            />
          ))}
        </div>

        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-100">
          <div className="text-xs text-slate-500">
            Selected: <strong className="text-slate-800">{selectedUseOption.title}</strong>
            {selectedStation ? (
              <>
                {" "}at <strong className="text-slate-800">{selectedStation.station_name}</strong>
              </>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => void handleStartCheck()}
            disabled={loadingResult || !stationCode}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-600 px-8 py-3.5 text-sm font-bold text-white shadow-md hover:bg-cyan-500 transition-all disabled:opacity-50"
          >
            {loadingResult ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Assessing measured parameters…</span>
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                <span>Run screening</span>
              </>
            )}
          </button>
        </div>
      </div>

      {resultError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {resultError}
        </div>
      )}

      {/* Step 3: backend result */}
      {assessments && (
        <div className="rounded-3xl border-2 border-cyan-500 bg-white p-6 sm:p-8 shadow-xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
            <div>
              <span className="text-[10px] font-extrabold uppercase tracking-widest text-cyan-700">
                HydraSense screening result
              </span>
              <h2 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight mt-0.5">
                {activeAssessment?.result_label ?? "No supported screening profile"}
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                {selectedStation?.station_name} · {selectedUseOption.title} · ruleset{" "}
                {rulesetVersion ?? "—"}
              </p>
            </div>
            {activeAssessment && (
              <span
                className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-extrabold uppercase tracking-wider ${resultStyles}`}
                data-testid="screening-result"
                data-result={activeAssessment.result}
              >
                {activeAssessment.result === "preliminary_suitable" ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : activeAssessment.result === "outside_limits" ? (
                  <ShieldAlert className="h-4 w-4" />
                ) : (
                  <AlertTriangle className="h-4 w-4" />
                )}
                <span>{activeAssessment.result.replace(/_/g, " ")}</span>
              </span>
            )}
          </div>

          {!activeAssessment ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              The backend returned no screening profile for this intended use. It is
              reported as unsupported rather than manufactured from partial data.
            </div>
          ) : (
            <>
              <p className="text-sm text-slate-700 leading-relaxed">
                {activeAssessment.summary}
              </p>

              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-bold">
                  {activeAssessment.data_quality.freshness.replace(/_/g, " ")}
                </span>
                {activeAssessment.data_quality.age_seconds !== null && (
                  <span>Reading age: {Math.round(activeAssessment.data_quality.age_seconds)} s</span>
                )}
                {activeAssessment.data_quality.device_source && (
                  <span>Source: {activeAssessment.data_quality.device_source}</span>
                )}
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Measured parameters and applied rules
                </h3>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[520px] text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wider text-slate-400">
                        <th className="py-1.5 pr-3 font-bold">Parameter</th>
                        <th className="py-1.5 pr-3 font-bold">Measured</th>
                        <th className="py-1.5 pr-3 font-bold">Reference criterion</th>
                        <th className="py-1.5 font-bold">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeAssessment.parameters.map((parameter) => (
                        <tr key={parameter.parameter} className="border-b border-slate-50 align-top">
                          <td className="py-2 pr-3 font-semibold text-slate-700">
                            {parameter.label}
                          </td>
                          <td className="py-2 pr-3 text-slate-600">
                            {scoreLabel(parameter.value, parameter.unit)}
                          </td>
                          <td className="py-2 pr-3 text-slate-500">{parameter.reference}</td>
                          <td className="py-2">
                            <span
                              className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold ${PARAMETER_STYLES[parameter.status] ?? PARAMETER_STYLES.not_measured}`}
                            >
                              {parameter.status_label}
                            </span>
                            {parameter.note && (
                              <p className="mt-1 text-[10px] text-slate-400">{parameter.note}</p>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {activeAssessment.missing_parameters.length > 0 && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                    Required tests still missing
                  </h3>
                  <ul className="mt-2 space-y-1.5">
                    {activeAssessment.missing_parameters.map((missing) => (
                      <li key={missing.parameter} className="flex items-start gap-2 text-[11px] text-slate-600">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                        <span>
                          <strong className="font-semibold text-slate-700">{missing.label}</strong> — {missing.why}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {activeAssessment.limitations.length > 0 && (
                <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                  {activeAssessment.limitations.map((limitation) => (
                    <p key={limitation} className="text-[11px] leading-relaxed text-slate-500">
                      {limitation}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-[11px] text-slate-500 leading-relaxed">
            <strong>Scope notice:</strong> this is a rule-based screening of the four
            measured parameters against a documented threshold profile. It is not a
            laboratory certificate, does not confirm the water is safe to drink, and
            cannot detect microbiological or chemical hazards that these sensors do not
            measure. The turbidity sensor is a relative index until calibrated against
            NTU references.
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <button
              type="button"
              onClick={() => setAssessments(null)}
              className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 hover:text-slate-900"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Check another use or station
            </button>
            {selectedStation && (
              <Link
                to={`/public/source/${selectedStation.station_code}`}
                className="text-xs font-bold text-cyan-700 hover:text-cyan-800"
              >
                Open station page →
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
