import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Droplets,
  Filter,
  History,
  Loader2,
  ShieldAlert,
  X,
} from "lucide-react";
import type { ApiError, ProductWaterTestSummary } from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken } from "../../lib/auth";

const STATUS_STYLES: Record<
  string,
  { badge: string; icon: typeof CheckCircle2 }
> = {
  WITHIN_PROJECT_TARGETS: {
    badge: "bg-emerald-50 text-emerald-800 border-emerald-200",
    icon: CheckCircle2,
  },
  REVIEW_RECOMMENDED: {
    badge: "bg-amber-50 text-amber-900 border-amber-200",
    icon: AlertTriangle,
  },
  NOT_RECOMMENDED_BY_SCREENING: {
    badge: "bg-orange-50 text-orange-900 border-orange-200",
    icon: ShieldAlert,
  },
  INCONCLUSIVE: {
    badge: "bg-slate-100 text-slate-700 border-slate-300",
    icon: AlertTriangle,
  },
  within_limits: { badge: "bg-emerald-50 text-emerald-800 border-emerald-200", icon: CheckCircle2 },
  potential_concern: { badge: "bg-amber-50 text-amber-900 border-amber-200", icon: AlertTriangle },
  outside_reference_range: {
    badge: "bg-orange-50 text-orange-900 border-orange-200",
    icon: ShieldAlert,
  },
  unable_to_assess: { badge: "bg-slate-100 text-slate-700 border-slate-300", icon: AlertTriangle },
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function UserHistory() {
  const navigate = useNavigate();
  const [tests, setTests] = useState<ProductWaterTestSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filters, setFilters] = useState<{ from?: string; to?: string }>({});

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }
    try {
      const result = await productApi.getTests(token, {
        limit: 100,
        dateFrom: filters.from,
        dateTo: filters.to,
      });
      setTests(result.items);
      setTotal(result.total);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setError(apiError.detail || "Unable to load your water-test history.");
    } finally {
      setLoading(false);
    }
  }, [filters, navigate]);

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

  const applyFilters = (event: React.FormEvent) => {
    event.preventDefault();
    if (dateFrom && dateTo && dateFrom > dateTo) {
      setError("The start date must be on or before the end date.");
      return;
    }
    setError(null);
    setLoading(true);
    setFilters({ from: dateFrom || undefined, to: dateTo || undefined });
  };

  const clearFilters = () => {
    setDateFrom("");
    setDateTo("");
    setLoading(true);
    setFilters({});
  };

  const filtersActive = Boolean(filters.from || filters.to);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link
            to="/user/dashboard"
            className="mb-4 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to Dashboard
          </Link>
          <h1 className="text-2xl font-bold text-slate-900">Test History</h1>
          <p className="mt-1 text-sm text-slate-500">
            Your private water-screening log. Results are visible only to your account.
          </p>
        </div>
        <Link
          to="/user/check-water"
          className="inline-flex w-fit items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-700"
        >
          <Droplets className="h-4 w-4" aria-hidden="true" />
          New Water Test
        </Link>
      </div>

      <form
        onSubmit={applyFilters}
        className="grid grid-cols-1 items-end gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-[1fr_1fr_auto_auto]"
      >
        <div>
          <label htmlFor="date-from" className="block text-xs font-bold text-slate-600">
            From date
          </label>
          <input
            id="date-from"
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(event) => setDateFrom(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />
        </div>
        <div>
          <label htmlFor="date-to" className="block text-xs font-bold text-slate-600">
            To date
          </label>
          <input
            id="date-to"
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(event) => setDateTo(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"
        >
          <Filter className="h-4 w-4" aria-hidden="true" />
          Apply
        </button>
        {filtersActive && (
          <button
            type="button"
            onClick={clearFilters}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
            Clear
          </button>
        )}
      </form>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{error}</p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="text-xs font-bold underline"
          >
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white py-16 text-sm text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-600" aria-hidden="true" />
          Loading your tests…
        </div>
      ) : tests.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <History className="mx-auto h-10 w-10 text-slate-300" aria-hidden="true" />
          <h2 className="mt-3 text-lg font-bold text-slate-900">
            {filtersActive ? "No tests in this date range" : "No water tests yet"}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {filtersActive
              ? "Try a wider date range or clear the filters."
              : "Run your first test to see a screening assessment and save it here."}
          </p>
          <Link
            to="/user/check-water"
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-700"
          >
            <Droplets className="h-4 w-4" aria-hidden="true" />
            Start a water test
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
            <h2 className="text-sm font-bold text-slate-800">
              {total} saved {total === 1 ? "test" : "tests"}
            </h2>
            {filtersActive && (
              <span className="text-xs text-slate-500">
                Filtered by saved date
              </span>
            )}
          </div>
          <ul className="divide-y divide-slate-100">
            {tests.map((test) => {
              const style = STATUS_STYLES[test.overall_status] ?? STATUS_STYLES.unable_to_assess;
              const Icon = style.icon;
              return (
                <li key={test.id}>
                  <Link
                    to={`/user/tests/${test.id}`}
                    className="flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-start gap-3">
                      <span className={`rounded-xl border p-2.5 ${style.badge}`}>
                        <Icon className="h-5 w-5" aria-hidden="true" />
                      </span>
                      <div>
                        <p className="text-sm font-bold text-slate-900">
                          {test.water_source_label} · {test.intended_use_label}
                          {test.reading_mode === "demo" && (
                            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-800">
                              Simulated
                            </span>
                          )}
                        </p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
                          <span>{test.test_code}</span>
                          <span aria-hidden="true">·</span>
                          <span className="inline-flex items-center gap-1">
                            <Clock className="h-3 w-3" aria-hidden="true" />
                            {formatDateTime(test.created_at)}
                          </span>
                          {test.ph !== null && <span>pH {test.ph}</span>}
                          {test.tds !== null && <span>TDS {test.tds} mg/L</span>}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 pl-14 sm:pl-0">
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${style.badge}`}
                      >
                        {test.overall_label}
                      </span>
                      <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-xs leading-relaxed text-amber-900">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          <strong>Private by default.</strong> These results are not shared with any
          authority automatically. Each screening is preliminary and is not a laboratory
          safety certification.
        </p>
      </div>
    </div>
  );
}
