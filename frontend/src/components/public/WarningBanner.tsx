import { AlertTriangle, ShieldAlert, Info, MapPin } from "lucide-react";
import type { WaterSource } from "../../data/mockData";

interface WarningBannerProps {
  sources: WaterSource[];
}

export default function WarningBanner({ sources }: WarningBannerProps) {
  const warningSources = sources.filter((s) => s.publicWarning || s.risk === "Critical" || s.risk === "High");

  if (warningSources.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5 flex items-center gap-3.5">
        <div className="rounded-xl bg-emerald-100 p-2.5 text-emerald-700">
          <Info className="h-5 w-5" />
        </div>
        <div>
          <h4 className="text-sm font-bold text-emerald-900">No Active Critical Water Warnings</h4>
          <p className="text-xs text-emerald-700 mt-0.5">All monitored public lakes and reservoirs are within acceptable seasonal advisory limits.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {warningSources.map((source) => {
        const isCritical = source.risk === "Critical";
        return (
          <div
            key={source.id}
            className={`rounded-2xl border p-5 transition-all ${
              isCritical
                ? "border-red-200 bg-red-50/70 text-red-950"
                : "border-amber-200 bg-amber-50/70 text-amber-950"
            }`}
          >
            <div className="flex items-start gap-3.5">
              <div className={`rounded-xl p-2.5 shrink-0 ${
                isCritical ? "bg-red-100 text-red-600" : "bg-amber-100 text-amber-700"
              }`}>
                {isCritical ? <ShieldAlert className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
              </div>

              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${
                    isCritical ? "bg-red-600 text-white" : "bg-amber-600 text-white"
                  }`}>
                    {source.risk} Advisory
                  </span>
                  <span className="text-xs font-semibold text-slate-500">
                    Updated {source.updatedTime}
                  </span>
                </div>

                <h3 className="mt-1 text-base font-bold text-slate-900">
                  {source.name}
                </h3>
                
                <div className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                  <MapPin className="h-3.5 w-3.5" />
                  <span>{source.location}</span>
                </div>

                <p className="mt-2 text-xs font-medium leading-relaxed text-slate-700">
                  {source.publicMessage}
                </p>

                <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                  <span className="rounded-lg bg-white/80 px-2.5 py-1 font-semibold text-slate-700 border border-slate-200/60">
                    Drinking: <strong className="text-red-600">{source.publicSuitability.drinking}</strong>
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
