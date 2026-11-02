import type { WaterSource } from "../../data/mockData";
import { MapPin, Clock, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

interface PublicSourceCardProps {
  source: WaterSource;
}

export default function PublicSourceCard({ source }: PublicSourceCardProps) {
  const getStatusBadge = (risk: WaterSource["risk"]) => {
    switch (risk) {
      case "Stable":
        return {
          label: "Normal / Stable",
          badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
          dotClass: "bg-emerald-500",
          icon: CheckCircle2,
        };
      case "Watch":
        return {
          label: "Advisory / Watch",
          badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
          dotClass: "bg-amber-500",
          icon: AlertTriangle,
        };
      case "High":
        return {
          label: "High Caution",
          badgeClass: "bg-orange-50 text-orange-700 border-orange-200",
          dotClass: "bg-orange-500",
          icon: AlertTriangle,
        };
      case "Critical":
        return {
          label: "Critical Warning",
          badgeClass: "bg-red-50 text-red-700 border-red-200",
          dotClass: "bg-red-500",
          icon: ShieldAlert,
        };
      default:
        return {
          label: "Monitored",
          badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
          dotClass: "bg-slate-500",
          icon: CheckCircle2,
        };
    }
  };

  const status = getStatusBadge(source.risk);
  const StatusIcon = status.icon;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs hover:border-slate-300 hover:shadow-sm transition-all duration-200 flex flex-col justify-between">
      <div>
        {/* Card Header: Type & Status Badge */}
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            {source.type}
          </span>
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-bold ${status.badgeClass}`}>
            <StatusIcon className="h-3.5 w-3.5" />
            {status.label}
          </span>
        </div>

        {/* Source Name & Location */}
        <h3 className="mt-2.5 text-lg font-bold tracking-tight text-slate-900">
          {source.name}
        </h3>
        <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
          <MapPin className="h-3.5 w-3.5 text-slate-400 shrink-0" />
          <span>{source.location}</span>
        </div>

        {/* Public Warning Alert Banner if active */}
        {source.publicWarning && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-3 flex items-start gap-2.5">
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs font-medium text-amber-900 leading-relaxed">
              {source.publicMessage}
            </p>
          </div>
        )}

        {/* Public Suitability Screening Matrix */}
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Use Suitability Screening
          </p>
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="text-slate-600 font-medium">Drinking</span>
              <span className={`font-bold ${
                source.publicSuitability.drinking === "Permissible with Treatment" ? "text-emerald-600" :
                source.publicSuitability.drinking === "Caution" ? "text-amber-600" : "text-red-600"
              }`}>{source.publicSuitability.drinking}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="text-slate-600 font-medium">Domestic</span>
              <span className={`font-bold ${
                source.publicSuitability.domestic === "Safe" ? "text-emerald-600" :
                source.publicSuitability.domestic === "Caution" ? "text-amber-600" : "text-red-600"
              }`}>{source.publicSuitability.domestic}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="text-slate-600 font-medium">Irrigation</span>
              <span className={`font-bold ${
                source.publicSuitability.irrigation === "Safe" ? "text-emerald-600" :
                source.publicSuitability.irrigation === "Caution" ? "text-amber-600" : "text-red-600"
              }`}>{source.publicSuitability.irrigation}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Card Footer */}
      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] font-medium text-slate-400">
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          <span>Updated {source.updatedTime}</span>
        </div>
        <span className="text-slate-500 font-semibold">Sensor Screening</span>
      </div>
    </div>
  );
}
