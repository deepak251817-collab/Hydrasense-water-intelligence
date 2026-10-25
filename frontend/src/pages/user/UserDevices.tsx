import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Cpu,
  Loader2,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { ApiError, ProductDevice, ProductDeviceStatus } from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken } from "../../lib/auth";

export default function UserDevices() {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<ProductDevice[]>([]);
  const [status, setStatus] = useState<ProductDeviceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }

    try {
      const userDevices = await productApi.getDevices(token);
      setDevices(userDevices);
      if (userDevices.some((device) => device.status === "ACTIVE")) {
        try {
          setStatus(await productApi.getDeviceStatus(token));
        } catch {
          setStatus(null);
        }
      } else {
        setStatus(null);
      }
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.detail || "Failed to load devices");
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
      }
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

  const getStatusColor = (value: string) => {
    switch (value) {
      case "ACTIVE":
        return "bg-emerald-100 text-emerald-700";
      case "PENDING_ACTIVATION":
        return "bg-amber-100 text-amber-700";
      default:
        return "bg-slate-100 text-slate-700";
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <Link
          to="/user/dashboard"
          className="mb-4 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Dashboard
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">My Devices</h1>
            <p className="mt-1 text-sm text-slate-500">
              Registered HydraSense personal testing devices.
            </p>
          </div>
          <Link
            to="/user/activate"
            className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-800"
          >
            Activate product code
          </Link>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin text-cyan-600" aria-hidden="true" />
          Loading devices…
        </div>
      )}

      {error && (
        <div className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {!loading && devices.length === 0 && !error && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white py-12 text-center">
          <Cpu className="mx-auto mb-3 h-12 w-12 text-slate-400" aria-hidden="true" />
          <p className="text-sm font-semibold text-slate-600">No devices registered yet</p>
          <p className="mt-1 text-xs text-slate-500">
            Activate your HydraSense product code to get started.
          </p>
        </div>
      )}

      {!loading &&
        devices.map((device) => {
          const isActive = device.status === "ACTIVE";
          return (
            <div
              key={device.id}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-center gap-4">
                  <div className={`${getStatusColor(device.status)} rounded-xl p-3`}>
                    <Cpu className="h-8 w-8" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="font-mono text-xs text-slate-400">{device.device_id}</p>
                    <h2 className="font-bold text-slate-900">HydraSense Tester</h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Product Code: {device.product_code}
                    </p>
                  </div>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${getStatusColor(device.status)}`}
                >
                  {device.status.replace("_", " ")}
                </span>
              </div>

              {isActive ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-center">
                      <CheckCircle2 className="mx-auto mb-1 h-5 w-5 text-emerald-500" aria-hidden="true" />
                      <p className="text-xs font-semibold text-slate-700">Registered</p>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-center">
                      {status?.connected ? (
                        <Wifi className="mx-auto mb-1 h-5 w-5 text-cyan-500" aria-hidden="true" />
                      ) : (
                        <WifiOff className="mx-auto mb-1 h-5 w-5 text-amber-500" aria-hidden="true" />
                      )}
                      <p className="text-xs font-semibold text-slate-700">
                        {status ? (status.connected ? "Connected" : "Offline") : "Status unavailable"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-center">
                      <Clock className="mx-auto mb-1 h-5 w-5 text-slate-500" aria-hidden="true" />
                      <p className="text-xs font-semibold text-slate-700">
                        {status?.last_seen
                          ? new Date(status.last_seen).toLocaleTimeString(undefined, {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "No reading"}
                      </p>
                    </div>
                  </div>
                  {status && (
                    <p className="text-xs text-slate-500">{status.note}</p>
                  )}
                </div>
              ) : (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-xs text-amber-800">
                    This device is not activated. Enter its product code to claim it.
                  </p>
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
