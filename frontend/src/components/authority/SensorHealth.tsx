import type { SensorProbe } from "../../data/mockData";
import { Battery, BatteryCharging, Server, Activity } from "lucide-react";

interface SensorHealthProps {
  probes: SensorProbe[];
}

export default function SensorHealth({ probes }: SensorHealthProps) {
  const getStatusStyles = (status: SensorProbe["status"]) => {
    switch (status) {
      case "Healthy":
        return {
          badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
          dot: "bg-emerald-500",
        };
      case "Warning":
        return {
          badge: "bg-amber-50 text-amber-700 border-amber-200",
          dot: "bg-amber-500",
        };
      case "Offline":
        return {
          badge: "bg-red-50 text-red-700 border-red-200",
          dot: "bg-red-500",
        };
      default:
        return {
          badge: "bg-slate-50 text-slate-700 border-slate-200",
          dot: "bg-slate-500",
        };
    }
  };

  const getSignalColor = (strength: SensorProbe["signalStrength"]) => {
    switch (strength) {
      case "Excellent":
      case "Good":
        return "text-emerald-600";
      case "Fair":
        return "text-amber-600";
      case "Poor":
        return "text-red-600";
      default:
        return "text-slate-500";
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <div className="flex items-center gap-2.5">
          <Server className="h-5 w-5 text-slate-700" />
          <h2 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
            IoT Probe Diagnostics
          </h2>
        </div>
        <span className="rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 text-[10px] font-bold text-slate-600">
          {probes.length} Probes Online
        </span>
      </div>

      {/* Probes List */}
      <div className="mt-4 flex-1 space-y-3">
        {probes.map((probe) => {
          const statusStyle = getStatusStyles(probe.status);
          const BatteryIcon = probe.battery > 50 ? Battery : BatteryCharging;

          return (
            <div
              key={probe.id}
              className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-3.5 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-white p-2 text-slate-700 border border-slate-200 shadow-xs">
                  <Activity className="h-4 w-4 text-cyan-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-xs font-bold text-slate-900">
                      {probe.parameter}
                    </h4>
                    <span className="text-[10px] font-mono font-bold text-cyan-700 bg-cyan-50 px-1.5 py-0.2 rounded">
                      {probe.currentValue}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-400 font-medium">
                    <span>Signal: <strong className={getSignalColor(probe.signalStrength)}>{probe.signalStrength}</strong></span>
                    <span>•</span>
                    <span>Uptime: <strong className="text-slate-600">{probe.lastUptime}</strong></span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3.5">
                <div className="flex items-center gap-1 text-xs font-bold text-slate-600" title={`Battery: ${probe.battery}%`}>
                  <BatteryIcon className={`h-4 w-4 ${probe.battery < 50 ? "text-amber-500" : "text-slate-400"}`} />
                  <span>{probe.battery}%</span>
                </div>

                <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider ${statusStyle.badge}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${statusStyle.dot}`} />
                  {probe.status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
