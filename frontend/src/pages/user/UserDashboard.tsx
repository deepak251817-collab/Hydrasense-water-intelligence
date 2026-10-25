import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Droplets,
  History,
  Loader2,
  LogOut,
  RefreshCw,
  ShieldAlert,
  WifiOff,
} from "lucide-react";
import type { ApiError, ProductAlertList, ProductOverview } from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken, getUser } from "../../lib/auth";
import type { AuthUser } from "../../lib/auth";

function relativeTime(value: string | null | undefined): string {
  if (!value) return "No measurements yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const seconds = Math.max(Math.floor((Date.now() - date.getTime()) / 1000), 0);
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function statusColor(status: string): string {
  switch (status) {
    case "WITHIN_PROJECT_TARGETS":
    case "within_limits":
      return "text-emerald-700 bg-emerald-50 border-emerald-200";
    case "REVIEW_RECOMMENDED":
    case "potential_concern":
      return "text-amber-800 bg-amber-50 border-amber-200";
    case "NOT_RECOMMENDED_BY_SCREENING":
    case "outside_reference_range":
      return "text-orange-800 bg-orange-50 border-orange-200";
    default:
      return "text-slate-700 bg-slate-50 border-slate-200";
  }
}

export default function UserDashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(getUser());
  const [overview, setOverview] = useState<ProductOverview | null>(null);
  const [alerts, setAlerts] = useState<ProductAlertList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }
    try {
      const [profile, summary, alertList] = await Promise.all([
        productApi.getProfile(token),
        productApi.getOverview(token),
        productApi.getAlerts(token).catch(() => null),
      ]);
      setUser({
        id: profile.id,
        email: profile.email,
        full_name: profile.full_name,
        role: profile.role,
      });
      setOverview(summary);
      setAlerts(alertList);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setError(apiError.detail || "Unable to load your dashboard.");
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      if (active) await load();
    })();
    return () => {
      active = false;
    };
  }, [load]);

  const handleLogout = () => {
    clearAuth();
    navigate("/user/login");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-600" aria-hidden="true" />
        Loading your dashboard…
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-red-500" aria-hidden="true" />
        <p className="mt-3 text-sm font-semibold text-red-800">
          {error || "Unable to load your profile."}
        </p>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            load();
          }}
          className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"
        >
          Try again
        </button>
      </div>
    );
  }

  const device = overview?.device ?? null;
  const latest = overview?.latest_test ?? null;
  const reading = device?.reading ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Welcome back, {user.full_name}. Your water tests are private to your account.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/user/check-water"
            className="flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-cyan-700"
          >
            <Droplets className="h-4 w-4" aria-hidden="true" />
            New Water Test
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-200"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Logout
          </button>
        </div>
      </div>

      {alerts && alerts.total > 0 && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-bold text-red-900">
                  Danger-level alerts for your water
                </h2>
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-800">
                  {alerts.critical_count} critical
                </span>
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                  {alerts.warning_count} warning
                </span>
              </div>
              <ul className="mt-3 space-y-3">
                {alerts.items.slice(0, 5).map((alert, index) => (
                  <li
                    key={`${alert.parameter}-${index}`}
                    className="rounded-xl border border-red-100 bg-white p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          alert.severity === "critical"
                            ? "bg-red-100 text-red-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {alert.severity === "critical" ? "CRITICAL" : "WARNING"}
                      </span>
                      <p className="text-xs font-bold text-slate-900">{alert.title}</p>
                      {alert.simulated && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-800">
                          Simulated source
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-xs text-slate-700">
                      {alert.label}
                      {alert.value !== null && (
                        <>
                          {" "}is <strong>{alert.value} {alert.unit}</strong>
                        </>
                      )}
                      {alert.reference && (
                        <span className="text-slate-500"> · {alert.reference}</span>
                      )}
                    </p>
                    <p className="mt-1 text-xs text-slate-600">{alert.message}</p>
                    <p className="mt-1 text-xs font-semibold text-cyan-800">
                      Next step: {alert.next_step}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {alerts && alerts.total === 0 && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-semibold text-emerald-800">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          No danger-level alerts from your recent readings or tests.
        </div>
      )}

      {!device && !loading && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-bold text-amber-900">No device linked yet</h2>
              <p className="mt-1 text-sm text-amber-800">
                Activate the product code supplied with your HydraSense tester to start
                water testing.
              </p>
              <Link
                to="/user/activate"
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-amber-900 px-3 py-2 text-xs font-bold text-white hover:bg-amber-800"
              >
                Activate product code
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-700">Device status</h2>
            <span className="rounded-lg bg-slate-100 p-2 text-slate-500">
              <Cpu className="h-4 w-4" aria-hidden="true" />
            </span>
          </div>
          <p className="text-2xl font-extrabold text-slate-900">
            {device ? (device.connected ? "Connected" : "Offline") : "Not linked"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {device ? `${device.device_name} · ${device.device_id}` : "Activate a product code"}
          </p>
          {device && (
            <p className="mt-2 text-xs text-slate-500">
              {device.note} <span className="text-slate-400">({relativeTime(device.last_seen)})</span>
            </p>
          )}
          <div className="mt-auto flex items-center gap-3 pt-3">
            {device && (
              <button
                type="button"
                onClick={() => {
                  setLoading(true);
                  load();
                }}
                className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-600 hover:text-slate-900"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Refresh
              </button>
            )}
            <Link
              to="/user/devices"
              className="text-xs font-bold text-cyan-700 hover:text-cyan-800"
            >
              View device
            </Link>
          </div>
        </div>

        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-700">Total tests</h2>
            <span className="rounded-lg bg-cyan-50 p-2 text-cyan-600">
              <Activity className="h-4 w-4" aria-hidden="true" />
            </span>
          </div>
          <p className="text-2xl font-extrabold text-slate-900">{overview?.total_tests ?? 0}</p>
          <p className="mt-1 text-xs text-slate-500">Private water checks saved</p>
          <Link
            to="/user/history"
            className="mt-auto pt-3 text-xs font-bold text-cyan-700 hover:text-cyan-800"
          >
            View history
          </Link>
        </div>

        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-700">Latest assessment</h2>
            <span className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
              <History className="h-4 w-4" aria-hidden="true" />
            </span>
          </div>
          {latest ? (
            <>
              <span
                className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${statusColor(latest.overall_status)}`}
              >
                {latest.overall_status === "WITHIN_PROJECT_TARGETS" ? (
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {latest.overall_label}
              </span>
              <p className="mt-2 text-xs text-slate-500">
                {latest.water_source_label} · {latest.intended_use_label}
              </p>
              <Link
                to={`/user/tests/${latest.id}`}
                className="mt-auto pt-3 text-xs font-bold text-cyan-700 hover:text-cyan-800"
              >
                Open assessment
              </Link>
            </>
          ) : (
            <p className="text-sm text-slate-500">
              No assessment yet. Run your first water test.
            </p>
          )}
        </div>
      </div>

      {/* Current readings */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-bold text-slate-800">Current device readings</h2>
          <span className="text-xs text-slate-500">
            {reading ? `${reading.source} · ${relativeTime(reading.timestamp)}` : "No reading"}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "pH", value: reading?.ph ?? null, unit: "" },
            { label: "TDS", value: reading?.tds ?? null, unit: "mg/L" },
            {
              label: "Turbidity Index",
              value: reading?.turbidity ?? null,
              unit:
                reading?.turbidity_unit === "ntu"
                  ? "NTU (calibrated)"
                  : reading?.turbidity_unit === "relative_index_0_100"
                    ? "0–100 index"
                    : "unit unknown",
            },
            { label: "Temperature", value: reading?.temperature ?? null, unit: "°C" },
          ].map((item) => (
            <div key={item.label} className="rounded-xl bg-slate-50 p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                {item.label}
              </p>
              <p className="mt-1 text-lg font-extrabold text-slate-900">
                {item.value ?? "—"}
                {item.unit && (
                  <span className="ml-1 text-[11px] font-semibold text-slate-500">
                    {item.unit}
                  </span>
                )}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-400">
          The turbidity index is a provisional 0–100 value (higher = cloudier), not a
          calibrated NTU measurement, and is never compared with NTU limits.
        </p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="font-bold text-slate-900">Recent tests</h2>
          <Link
            to="/user/history"
            className="inline-flex items-center gap-1 text-sm font-semibold text-cyan-700 hover:text-cyan-800"
          >
            View all <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {overview && overview.recent_tests.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {overview.recent_tests.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/user/tests/${item.id}`}
                  className="flex flex-col gap-2 px-5 py-4 hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-start gap-3">
                    <span className={`rounded-lg border p-2 ${statusColor(item.overall_status)}`}>
                      {item.overall_status === "WITHIN_PROJECT_TARGETS" ? (
                        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                      )}
                    </span>
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        {item.water_source_label} · {item.intended_use_label}
                        {item.reading_mode === "demo" && (
                          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-800">
                            Simulated
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-slate-500">
                        {relativeTime(item.created_at)} · {item.test_code}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 pl-11 sm:pl-0">
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${statusColor(item.overall_status)}`}>
                      {item.overall_label}
                    </span>
                    <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-5 py-10 text-center">
            <History className="mx-auto h-8 w-8 text-slate-300" aria-hidden="true" />
            <p className="mt-2 text-sm font-semibold text-slate-600">No tests yet</p>
            <p className="mt-1 text-xs text-slate-500">
              Your first screening will appear here.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
