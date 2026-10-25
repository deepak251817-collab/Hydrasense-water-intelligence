import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Droplets,
  FlaskConical,
  Gauge,
  History,
  Info,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Thermometer,
  Waves,
  WifiOff,
} from "lucide-react";
import type {
  ApiError,
  ProductReadingAssessment,
  ProductWaterTest,
  ProductWaterTestSummary,
} from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken } from "../../lib/auth";

const PARAMETER_ICONS: Record<string, typeof Droplets> = {
  ph: FlaskConical,
  tds: Gauge,
  turbidity: Waves,
  temperature: Thermometer,
};

const PARAMETER_ORDER = ["ph", "tds", "turbidity", "temperature"] as const;

const STATUS_STYLES: Record<
  string,
  { badge: string; icon: typeof CheckCircle2; accent: string }
> = {
  WITHIN_PROJECT_TARGETS: {
    badge: "bg-emerald-50 text-emerald-800 border-emerald-200",
    icon: CheckCircle2,
    accent: "border-emerald-200 bg-emerald-50/40",
  },
  REVIEW_RECOMMENDED: {
    badge: "bg-amber-50 text-amber-900 border-amber-200",
    icon: AlertTriangle,
    accent: "border-amber-200 bg-amber-50/40",
  },
  NOT_RECOMMENDED_BY_SCREENING: {
    badge: "bg-orange-50 text-orange-900 border-orange-200",
    icon: ShieldAlert,
    accent: "border-orange-200 bg-orange-50/40",
  },
  INCONCLUSIVE: {
    badge: "bg-slate-100 text-slate-700 border-slate-300",
    icon: Info,
    accent: "border-slate-300 bg-slate-50",
  },
  within_limits: {
    badge: "bg-emerald-50 text-emerald-800 border-emerald-200",
    icon: CheckCircle2,
    accent: "border-emerald-200 bg-emerald-50/40",
  },
  potential_concern: {
    badge: "bg-amber-50 text-amber-900 border-amber-200",
    icon: AlertTriangle,
    accent: "border-amber-200 bg-amber-50/40",
  },
  outside_reference_range: {
    badge: "bg-orange-50 text-orange-900 border-orange-200",
    icon: ShieldAlert,
    accent: "border-orange-200 bg-orange-50/40",
  },
  unable_to_assess: {
    badge: "bg-slate-100 text-slate-700 border-slate-300",
    icon: Info,
    accent: "border-slate-300 bg-slate-50",
  },
  insufficient_criteria: {
    badge: "bg-sky-50 text-sky-900 border-sky-200",
    icon: Info,
    accent: "border-sky-200 bg-sky-50/40",
  },
};

function statusStyle(status: string) {
  return STATUS_STYLES[status] ?? STATUS_STYLES.unable_to_assess;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatValue(reading: ProductReadingAssessment): string {
  if (reading.value === null || reading.value === undefined) return "Not measured";
  const digits = reading.parameter === "temperature" ? 1 : 2;
  return Number(reading.value.toFixed(digits)).toString();
}

/** The unit as reported for the measurement — never assumes NTU. */
function unitLabel(reading: ProductReadingAssessment): string {
  if (reading.unit) return reading.unit;
  return reading.parameter === "ph" ? "pH (dimensionless)" : "";
}

function ParameterCard({ reading }: { reading: ProductReadingAssessment }) {
  const Icon = PARAMETER_ICONS[reading.parameter] ?? Droplets;
  const style = statusStyle(reading.status);
  const StatusIcon = style.icon;
  const missing = reading.value === null || reading.value === undefined;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-slate-600">
          <Icon className="h-5 w-5" aria-hidden="true" />
          <h3 className="text-sm font-bold text-slate-800">{reading.label}</h3>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-bold ${style.badge}`}
        >
          <StatusIcon className="h-3.5 w-3.5" aria-hidden="true" />
          {reading.status_label}
        </span>
      </div>

      <p className="mt-4 flex flex-wrap items-baseline gap-1.5">
        <span className="text-3xl font-extrabold tracking-tight text-slate-900">
          {missing ? "—" : formatValue(reading)}
        </span>
        <span className="text-xs font-semibold text-slate-500">
          {missing ? "No value" : unitLabel(reading)}
        </span>
      </p>

      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        {reading.reference}
      </p>
      {reading.note && (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{reading.note}</p>
      )}
    </div>
  );
}

function StatusBadge({ status, label }: { status: string; label: string }) {
  const style = statusStyle(status);
  const Icon = style.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold ${style.badge}`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </span>
  );
}

function HistoryRow({ item, current }: { item: ProductWaterTestSummary; current: boolean }) {
  const style = statusStyle(item.overall_status);
  const Icon = style.icon;
  return (
    <Link
      to={`/user/tests/${item.id}`}
      className={`flex flex-col gap-3 rounded-xl border p-4 transition-colors hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between ${
        current ? "border-cyan-200 bg-cyan-50/40" : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className={`rounded-lg border p-2 ${style.badge}`}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-bold text-slate-900">
            {item.water_source_label} · {item.intended_use_label}
            {current && (
              <span className="ml-2 rounded bg-cyan-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-cyan-700">
                This test
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {formatDateTime(item.created_at)} · {item.test_code}
            {item.reading_mode === "demo" && " · Simulated data"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 pl-11 sm:pl-0">
        <span className={`text-xs font-bold ${style.badge.split(" ")[1] ?? "text-slate-700"}`}>
          {item.overall_label}
        </span>
        <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
      </div>
    </Link>
  );
}

export default function TestResult() {
  const { testId } = useParams<{ testId: string }>();
  const navigate = useNavigate();
  const [test, setTest] = useState<ProductWaterTest | null>(null);
  const [history, setHistory] = useState<ProductWaterTestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }
    const id = Number(testId);
    if (!Number.isFinite(id)) {
      setError("Invalid test reference.");
      setLoading(false);
      return;
    }

    try {
      const [detail, recent] = await Promise.all([
        productApi.getTest(id, token),
        productApi.getTests(token, { limit: 5 }),
      ]);
      setTest(detail);
      setHistory(recent.items);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setError(apiError.detail || "Unable to load this water assessment.");
    } finally {
      setLoading(false);
    }
  }, [navigate, testId]);

  useEffect(() => {
    let active = true;
    // Fetch after the effect body completes so state updates are not triggered
    // synchronously during the commit phase.
    void (async () => {
      await Promise.resolve();
      if (active) await load();
    })();
    return () => {
      active = false;
    };
  }, [load]);

  const readings = useMemo(
    () =>
      PARAMETER_ORDER.map((key) => test?.assessment.readings[key]).filter(
        (item): item is ProductReadingAssessment => Boolean(item)
      ),
    [test]
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-500">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-600" aria-hidden="true" />
        <p className="text-sm font-medium">Loading water assessment…</p>
      </div>
    );
  }

  if (error || !test) {
    return (
      <div className="mx-auto max-w-xl space-y-4 py-16 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-amber-500" aria-hidden="true" />
        <h1 className="text-xl font-bold text-slate-900">Assessment unavailable</h1>
        <p className="text-sm text-slate-600">
          {error || "This water test could not be found."}
        </p>
        <div className="flex justify-center gap-3">
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-800"
          >
            Try again
          </button>
          <Link
            to="/user/history"
            className="rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-200"
          >
            View history
          </Link>
        </div>
      </div>
    );
  }

  const { assessment } = test;
  const overallStyle = statusStyle(assessment.overall.status);
  const OverallIcon = overallStyle.icon;
  const suitabilityStyle = statusStyle(assessment.suitability.result);
  const SuitabilityIcon = suitabilityStyle.icon;
  const isDemo = assessment.data_quality.demo_mode || test.reading_mode === "demo";
  const isLiveHardware = !isDemo && test.reading_source === "esp32";

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <div>
        <Link
          to="/user/dashboard"
          className="mb-4 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Dashboard
        </Link>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-cyan-600">
              {test.test_code}
            </p>
            <h1 className="mt-1 text-2xl font-bold text-slate-900 sm:text-3xl">
              Water Quality Assessment
            </h1>
          </div>
          <Link
            to="/user/check-water"
            className="inline-flex w-fit items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-700"
          >
            <Droplets className="h-4 w-4" aria-hidden="true" />
            New Water Test
          </Link>
        </div>
      </div>

      {/* Top metadata: source, intended use, device, last measurement */}
      <div className="grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
            Water source
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">{test.water_source_label}</p>
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
            Intended use
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">
            {test.intended_use_label}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
            Device connection
          </p>
          <div className="mt-1 flex items-center gap-2 text-sm font-bold text-slate-900">
            {isDemo ? (
              <>
                <WifiOff className="h-4 w-4 text-amber-600" aria-hidden="true" />
                Simulated data
              </>
            ) : isLiveHardware ? (
              <>
                <Cpu className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                Live hardware reading
              </>
            ) : (
              <>
                <Info className="h-4 w-4 text-slate-500" aria-hidden="true" />
                {test.reading_source} reading
              </>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-500">{test.device_name}</p>
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
            Last measurement
          </p>
          <p className="mt-1 flex items-center gap-1.5 text-sm font-bold text-slate-900">
            <Clock className="h-4 w-4 text-slate-400" aria-hidden="true" />
            {formatDateTime(assessment.reading_timestamp ?? test.reading_timestamp)}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            Saved {formatDateTime(test.created_at)}
          </p>
        </div>
      </div>

      {isDemo && (
        <div className="flex gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <WifiOff className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p>
            <strong>Simulated readings — not real sensor data.</strong> This test used
            clearly labelled demo values because the physical device was not sending
            current measurements. Do not use it to judge real water.
          </p>
        </div>
      )}

      {/* Main result card */}
      <section
        className={`rounded-3xl border p-6 shadow-sm sm:p-8 ${overallStyle.accent}`}
        aria-labelledby="overall-result-heading"
      >
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <span className={`rounded-2xl border bg-white p-3 ${overallStyle.badge}`}>
              <OverallIcon className="h-7 w-7" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Current screening assessment
              </p>
              <h2
                id="overall-result-heading"
                className="mt-1 text-xl font-extrabold text-slate-900 sm:text-2xl"
              >
                {assessment.overall.label}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-700">
                {assessment.overall.summary}
              </p>
            </div>
          </div>
          <StatusBadge status={assessment.overall.status} label="Screening status" />
        </div>

        <div className="mt-5 flex gap-3 rounded-xl border border-slate-300/70 bg-white/80 p-4 text-xs leading-relaxed text-slate-700">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
          <p>
            <strong>Preliminary screening only.</strong> This is not a laboratory safety
            certification. Pathogens, heavy metals, pesticides and other unmeasured
            contaminants cannot be excluded from four sensor readings. Laboratory
            testing is required to confirm potability.
          </p>
        </div>
      </section>

      {/* Sensor readings */}
      <section aria-labelledby="readings-heading">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 id="readings-heading" className="text-lg font-bold text-slate-900">
              Sensor readings
            </h2>
            <p className="text-xs text-slate-500">
              Four measurements captured for this test · criteria {test.criteria_version}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {readings.map((reading) => (
            <ParameterCard key={reading.parameter} reading={reading} />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Parameters requiring attention */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">Parameters requiring attention</h2>
          {assessment.attention.length === 0 ? (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              <p>
                No monitored parameter requires attention. Unmeasured contaminants can
                still be present.
              </p>
            </div>
          ) : (
            <ul className="mt-4 space-y-3">
              {assessment.attention.map((item) => {
                const style = statusStyle(item.status);
                const Icon = style.icon;
                return (
                  <li
                    key={item.parameter}
                    className="flex items-start gap-3 rounded-xl border border-slate-200 p-3"
                  >
                    <span className={`rounded-lg border p-1.5 ${style.badge}`}>
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        {item.label}
                        {item.value !== null && (
                          <span className="ml-2 font-semibold text-slate-600">
                            {item.value} {item.unit}
                          </span>
                        )}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-600">{item.message}</p>
                      <p className="mt-1 text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        {item.status_label}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Why */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">
            Why did I get this result?
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Rule-based screening — not a trained prediction. Every concern is listed
            with its measured value, reference and next step.
          </p>
          {assessment.overall.reason_details &&
          assessment.overall.reason_details.length > 0 ? (
            <ul className="mt-4 space-y-3">
              {assessment.overall.reason_details.map((detail, index) => (
                <li
                  key={`${detail.parameter}-${index}`}
                  className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-bold text-slate-900">
                      {detail.label}
                    </span>
                    {detail.value !== null && (
                      <span className="text-xs font-semibold text-slate-600">
                        {detail.value} {detail.unit}
                      </span>
                    )}
                    <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-bold text-slate-600">
                      {detail.status_label}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-700">
                    {detail.reason}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                    Reference: {detail.reference}
                  </p>
                  {detail.calibration_limitation && (
                    <p className="mt-1 text-[11px] leading-relaxed text-amber-700">
                      Calibration/data quality: {detail.calibration_limitation}
                    </p>
                  )}
                  <p className="mt-1 text-[11px] font-semibold text-cyan-800">
                    Next step: {detail.next_step}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <ul className="mt-4 space-y-2.5">
              {assessment.overall.reasons.map((reason) => (
                <li key={reason} className="flex items-start gap-2 text-sm text-slate-700">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-500" />
                  {reason}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Suitability for selected purpose */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {test.intended_use_label} suitability
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {assessment.suitability.description}
            </p>
            <p className="mt-1 text-xs font-semibold text-slate-500">
              {assessment.suitability.standard}
            </p>
          </div>
          <span
            className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold ${suitabilityStyle.badge}`}
          >
            <SuitabilityIcon className="h-4 w-4" aria-hidden="true" />
            {assessment.suitability.result_label}
          </span>
        </div>

        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
          {assessment.suitability.summary}
        </p>

        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
          {assessment.suitability.criteria.map((criterion) => {
            const style = statusStyle(criterion.status);
            const Icon = style.icon;
            return (
              <div
                key={criterion.parameter}
                className="rounded-xl border border-slate-200 p-3.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-bold text-slate-800">{criterion.label}</p>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${style.badge}`}
                  >
                    <Icon className="h-3 w-3" aria-hidden="true" />
                    {criterion.status_label}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  {criterion.value !== null && criterion.value !== undefined
                    ? `${criterion.value} ${criterion.unit}`.trim()
                    : "No measurement"}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  {criterion.reference}
                </p>
              </div>
            );
          })}
        </div>

        {assessment.suitability.limitations.length > 0 && (
          <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-sky-800">
              Limitations for this use
            </p>
            <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-sky-900">
              {assessment.suitability.limitations.map((limitation) => (
                <li key={limitation} className="flex gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-sky-500" />
                  {limitation}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Prediction */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">Future prediction</h2>
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-slate-800">
                {assessment.prediction.available
                  ? "Prediction available"
                  : "Future prediction unavailable"}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                {assessment.prediction.message}
              </p>
              <p className="mt-2 text-[11px] text-slate-500">
                This result is a current rule-based screening, not a trained AI
                prediction, and no future readings are invented.
              </p>
            </div>
          </div>
        </section>

        {/* Next steps */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">Recommended next steps</h2>
          <ul className="mt-4 space-y-2.5">
            {assessment.next_steps.map((step) => (
              <li key={step} className="flex items-start gap-2 text-sm text-slate-700">
                <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600" aria-hidden="true" />
                {step}
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Data quality */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold text-slate-900">Sensor calibration and data quality</h2>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-700">
            {assessment.data_quality.demo_mode
              ? "Simulated data"
              : assessment.data_quality.calibration_status === "calibrated"
                ? "Calibrated"
                : assessment.data_quality.calibration_status === "provisional"
                  ? "Provisional calibration"
                  : "Calibration status unknown"}
            {" · "}
            {assessment.data_quality.freshness === "fresh"
              ? "Fresh reading"
              : assessment.data_quality.freshness === "stale"
                ? "Stale reading"
                : "Simulated"}
          </span>
        </div>
        {assessment.data_quality.stability && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            <span className="font-bold">Stability:</span>
            <span className="font-semibold">
              {assessment.data_quality.stability.status_label}
            </span>
            <span className="text-slate-500">
              {assessment.data_quality.stability.valid_samples} valid samples over{" "}
              {assessment.data_quality.stability.span_seconds.toFixed(0)} s
            </span>
            {assessment.data_quality.stability.status !== "stable" && (
              <span className="text-amber-700">
                {assessment.data_quality.stability.message}
              </span>
            )}
          </div>
        )}

        {assessment.data_quality.warnings.length === 0 &&
        assessment.data_quality.errors.length === 0 ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-emerald-700">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            No data-quality warnings were recorded for this test.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {[...assessment.data_quality.errors, ...assessment.data_quality.warnings].map(
              (warning) => (
                <li key={warning} className="flex items-start gap-2 text-xs text-slate-600">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
                  {warning}
                </li>
              )
            )}
          </ul>
        )}
        <p className="mt-3 text-[11px] text-slate-400">
          Test {test.test_code} · screening criteria {test.criteria_version}. Thresholds are
          configured screening values, not universal safety guarantees.
        </p>
      </section>

      {/* Previous tests */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <History className="h-5 w-5 text-slate-400" aria-hidden="true" />
            Previous tests
          </h2>
          <Link
            to="/user/history"
            className="inline-flex items-center gap-1 text-sm font-bold text-cyan-700 hover:text-cyan-800"
          >
            View history <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {history.filter((item) => item.id !== test.id).length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
            No earlier tests yet. Your next test will appear here.
          </p>
        ) : (
          <div className="space-y-3">
            {history
              .filter((item) => item.id !== test.id)
              .slice(0, 4)
              .map((item) => (
                <HistoryRow key={item.id} item={item} current={false} />
              ))}
          </div>
        )}
      </section>
    </div>
  );
}
