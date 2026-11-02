import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Cpu,
  Droplets,
  FlaskConical,
  Info,
  Loader2,
  RefreshCw,
  WifiOff,
} from "lucide-react";
import type {
  ApiError,
  IntendedUseCode,
  ProductDeviceStatus,
  WaterSourceCode,
} from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken } from "../../lib/auth";

const SOURCES: { code: WaterSourceCode; label: string; hint: string }[] = [
  { code: "tap", label: "Tap water", hint: "Municipal or household supply" },
  { code: "borewell", label: "Borewell water", hint: "Borewell / tube well" },
  { code: "well", label: "Well water", hint: "Open or covered well" },
  { code: "tank", label: "Tank water", hint: "Storage tank or sump" },
  { code: "surface", label: "River / lake / pond", hint: "Surface water body" },
  { code: "other", label: "Other source", hint: "Anything else" },
];

const USES: { code: IntendedUseCode; label: string; hint: string }[] = [
  { code: "drinking", label: "Drinking", hint: "Consumption and cooking" },
  { code: "domestic", label: "Domestic use", hint: "Bathing, washing, cleaning" },
  { code: "irrigation", label: "Irrigation", hint: "Garden, crops, landscaping" },
  { code: "general", label: "General non-potable", hint: "Cleaning, gardening, cooling" },
];

function formatAge(seconds: number | null): string {
  if (seconds === null) return "unknown";
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  return `${Math.floor(seconds / 60)} min ago`;
}

export default function UserCheckWater() {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [source, setSource] = useState<WaterSourceCode | null>(null);
  const [use, setUse] = useState<IntendedUseCode | null>(null);
  const [device, setDevice] = useState<ProductDeviceStatus | null>(null);
  const [deviceLoading, setDeviceLoading] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"live" | "demo" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string[]>([]);

  const loadDevice = useCallback(async () => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }
    setDeviceError(null);
    try {
      setDevice(await productApi.getDeviceStatus(token));
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setDeviceError(apiError.detail || "Unable to check device status.");
    } finally {
      setDeviceLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      if (active && step === 3) await loadDevice();
    })();
    return () => {
      active = false;
    };
  }, [step, loadDevice]);

  const runTest = async (mode: "live" | "demo") => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }
    if (!source || !use) return;

    setSubmitting(mode);
    setError(null);
    setErrorDetails([]);
    try {
      const result = await productApi.startTest(
        {
          water_source: source,
          intended_use: use,
          reading_mode: mode,
        },
        token
      );
      navigate(`/user/tests/${result.id}`);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setError(apiError.detail || "The water test could not be completed.");
      setErrorDetails(apiError.errors ?? []);
    } finally {
      setSubmitting(null);
    }
  };

  const selectedSource = SOURCES.find((item) => item.code === source);
  const selectedUse = USES.find((item) => item.code === use);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          to="/user/dashboard"
          className="mb-4 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Dashboard
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">New Water Test</h1>
        <p className="mt-1 text-sm text-slate-500">
          Screen your water with your HydraSense tester's four sensors: pH, TDS,
          turbidity and temperature.
        </p>
      </div>

      {/* Progress */}
      <ol className="grid grid-cols-3 gap-2" aria-label="Test progress">
        {[
          { number: 1, label: "Water source" },
          { number: 2, label: "Intended use" },
          { number: 3, label: "Run test" },
        ].map((item) => {
          const active = step === item.number;
          const done = step > item.number;
          return (
            <li
              key={item.number}
              className={`rounded-xl border px-3 py-2.5 ${
                active
                  ? "border-cyan-300 bg-cyan-50 text-cyan-800"
                  : done
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-slate-200 bg-white text-slate-500"
              }`}
              aria-current={active ? "step" : undefined}
            >
              <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide">
                {done ? (
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <span>{item.number}</span>
                )}
                {item.label}
              </p>
            </li>
          );
        })}
      </ol>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        {step === 1 && (
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              1. What type of water are you testing?
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              The selected source is stored with this private test.
            </p>
            <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {SOURCES.map((item) => {
                const active = source === item.code;
                return (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => {
                      setSource(item.code);
                      setStep(2);
                    }}
                    aria-pressed={active}
                    className={`rounded-xl border-2 p-4 text-left transition-colors ${
                      active
                        ? "border-cyan-500 bg-cyan-50"
                        : "border-slate-100 hover:border-cyan-400 hover:bg-cyan-50/50"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2 text-sm font-bold text-slate-800">
                      {item.label}
                      {active && <CheckCircle2 className="h-4 w-4 text-cyan-600" aria-hidden="true" />}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">{item.hint}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 className="text-lg font-bold text-slate-900">2. What will the water be used for?</h2>
            <p className="mt-1 text-sm text-slate-500">
              Suitability criteria differ by purpose. Drinking-water thresholds are not
              reused for irrigation or general non-potable use.
            </p>
            <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {USES.map((item) => {
                const active = use === item.code;
                return (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => {
                      setUse(item.code);
                      setDeviceLoading(true);
                      setStep(3);
                    }}
                    aria-pressed={active}
                    className={`rounded-xl border-2 p-4 text-left transition-colors ${
                      active
                        ? "border-cyan-500 bg-cyan-50"
                        : "border-slate-100 hover:border-cyan-400 hover:bg-cyan-50/50"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2 text-sm font-bold text-slate-800">
                      {item.label}
                      {active && <CheckCircle2 className="h-4 w-4 text-cyan-600" aria-hidden="true" />}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">{item.hint}</span>
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => setStep(1)}
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Back to water source
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900">3. Run the water test</h2>
              <p className="mt-1 text-sm text-slate-500">
                Live readings come from your device over the existing MQTT/backend flow.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                  Water source
                </p>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {selectedSource?.label ?? "Not selected"}
                </p>
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="mt-1 text-xs font-semibold text-cyan-700 hover:text-cyan-800"
                >
                  Change
                </button>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                  Intended use
                </p>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {selectedUse?.label ?? "Not selected"}
                </p>
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="mt-1 text-xs font-semibold text-cyan-700 hover:text-cyan-800"
                >
                  Change
                </button>
              </div>
            </div>

            {/* Device readiness */}
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                  <Cpu className="h-4 w-4 text-slate-400" aria-hidden="true" />
                  Device status
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setDeviceLoading(true);
                    setDeviceError(null);
                    loadDevice();
                  }}
                  disabled={deviceLoading}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-600 hover:text-slate-900 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${deviceLoading ? "animate-spin" : ""}`} aria-hidden="true" />
                  Refresh
                </button>
              </div>

              {deviceLoading && (
                <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Checking your device…
                </p>
              )}

              {!deviceLoading && deviceError && (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <p className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {deviceError}
                  </p>
                  <Link to="/user/activate" className="mt-2 inline-block font-bold underline">
                    Activate a product code
                  </Link>
                </div>
              )}

              {!deviceLoading && device && (
                <div className="mt-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${
                        device.connected
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : "border-amber-200 bg-amber-50 text-amber-900"
                      }`}
                    >
                      {device.connected ? (
                        <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
                      ) : (
                        <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
                      )}
                      {device.connected ? "Device connected" : "Device not connected"}
                    </span>
                    <span className="text-xs text-slate-500">
                      {device.device_name} · {device.device_id}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600">{device.note}</p>
                  {device.reading && (
                    <div className="grid grid-cols-2 gap-2 pt-1 text-xs text-slate-700 sm:grid-cols-4">
                      <span className="rounded-lg bg-slate-50 px-2 py-1.5">
                        pH <strong>{device.reading.ph ?? "—"}</strong>
                      </span>
                      <span className="rounded-lg bg-slate-50 px-2 py-1.5">
                        TDS <strong>{device.reading.tds ?? "—"}</strong> mg/L
                      </span>
                      <span className="rounded-lg bg-slate-50 px-2 py-1.5">
                        Turbidity{" "}
                        <strong>
                          {device.reading.turbidity ?? "—"}
                          {device.reading.turbidity_unit === "relative_index_0_100"
                            ? " (relative index)"
                            : device.reading.turbidity_unit === "ntu"
                              ? " NTU"
                              : ""}
                        </strong>
                      </span>
                      <span className="rounded-lg bg-slate-50 px-2 py-1.5">
                        Temp <strong>{device.reading.temperature ?? "—"}</strong> °C
                      </span>
                    </div>
                  )}
                  {device.last_seen && (
                    <p className="text-[11px] text-slate-500">
                      Last measurement {formatAge(device.reading_age_seconds)}.
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="flex gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 text-xs leading-relaxed text-blue-900">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>
                A live test requires a reading from the last 5 minutes plus a stable
                rolling window (at least 10 valid samples over 20 seconds). Keep the
                probe submerged and retry if the device is still stabilising. If no
                physical device is available, you can use clearly labelled demo readings
                to see how the assessment works — they are never presented as real sensor
                data.
              </p>
            </div>

            {error && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <p className="flex items-start gap-2 font-semibold">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  {error}
                </p>
                {errorDetails.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-6 text-xs">
                    {errorDetails.map((detail) => (
                      <li key={detail}>{detail}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => runTest("live")}
                disabled={submitting !== null}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-cyan-600 px-4 py-3 text-sm font-bold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {submitting === "live" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Droplets className="h-4 w-4" aria-hidden="true" />
                )}
                {submitting === "live" ? "Running screening…" : "Run live water test"}
              </button>
              <button
                type="button"
                onClick={() => runTest("demo")}
                disabled={submitting !== null}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting === "demo" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <FlaskConical className="h-4 w-4" aria-hidden="true" />
                )}
                Use simulated demo readings
              </button>
            </div>
            <p className="text-center text-[11px] text-slate-500">
              Demo readings are clearly labelled simulated data and are not a substitute
              for testing your water.
            </p>

            <button
              type="button"
              onClick={() => setStep(2)}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-900"
            >
              <ArrowRight className="h-4 w-4 rotate-180" aria-hidden="true" />
              Back to intended use
            </button>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs leading-relaxed text-amber-900">
        <p className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>Preliminary screening, not certification.</strong> These four sensors
            cannot detect pathogens, heavy metals, pesticides or other contaminants.
            Laboratory testing is required to confirm potability.
          </span>
        </p>
      </div>
    </div>
  );
}
