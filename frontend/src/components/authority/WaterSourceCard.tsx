import type { WaterSource } from "../../data/mockData";
import { MapPin, ShieldCheck, ShieldAlert, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface WaterSourceCardProps {
  source: WaterSource;
  isSelected?: boolean;
  onClick?: () => void;
}

export default function WaterSourceCard({ source, isSelected = false, onClick }: WaterSourceCardProps) {
  const getRiskStyles = (risk: WaterSource["risk"]) => {
    switch (risk) {
      case "Stable":
        return {
          badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
          dot: "bg-emerald-500",
          bar: "bg-emerald-500",
          scoreText: "text-emerald-600",
        };
      case "Watch":
        return {
          badge: "bg-amber-50 text-amber-700 border-amber-200",
          dot: "bg-amber-500",
          bar: "bg-amber-500",
          scoreText: "text-amber-600",
        };
      case "High":
        return {
          badge: "bg-orange-50 text-orange-700 border-orange-200",
          dot: "bg-orange-500",
          bar: "bg-orange-500",
          scoreText: "text-orange-600",
        };
      case "Critical":
        return {
          badge: "bg-red-50 text-red-700 border-red-200",
          dot: "bg-red-500",
          bar: "bg-red-500",
          scoreText: "text-red-600",
        };
      default:
        return {
          badge: "bg-slate-50 text-slate-700 border-slate-200",
          dot: "bg-slate-500",
          bar: "bg-slate-500",
          scoreText: "text-slate-600",
        };
    }
  };

  const styles = getRiskStyles(source.risk);

  const getTrendIcon = () => {
    switch (source.trendDirection) {
      case "improving":
        return <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />;
      case "deteriorating":
        return <TrendingDown className="h-3.5 w-3.5 text-red-500" />;
      default:
        return <Minus className="h-3.5 w-3.5 text-slate-400" />;
    }
  };

  return (
    <div
      onClick={onClick}
      className={`rounded-2xl border p-5 transition-all duration-200 cursor-pointer ${
        isSelected
          ? "border-cyan-600 bg-cyan-50/20 shadow-md ring-2 ring-cyan-600/30"
          : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-xs"
      }`}
    >
      {/* Top Details & Risk Tag */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              {source.type}
            </span>
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${styles.badge}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${styles.dot}`} />
              {source.risk}
            </span>
          </div>

          <h3 className="mt-1.5 text-base font-bold text-slate-900 tracking-tight">
            {source.name}
          </h3>

          <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
            <MapPin className="h-3.5 w-3.5 text-slate-400" />
            <span>{source.location}</span>
          </div>
        </div>

        {/* Circular Health Score */}
        <div className="flex flex-col items-center">
          <div className="relative flex h-12 w-12 items-center justify-center rounded-full border border-slate-100 bg-slate-50 shadow-inner">
            <span className={`text-base font-extrabold ${styles.scoreText}`}>
              {source.healthScore}
            </span>
          </div>
          <span className="mt-1 text-[9px] font-bold uppercase tracking-widest text-slate-400">
            Health
          </span>
        </div>
      </div>

      {/* Health Score Progress Bar */}
      <div className="mt-4">
        <div className="flex justify-between text-[11px] font-bold text-slate-500 mb-1">
          <span>Telemetry Index</span>
          <span>{source.healthScore}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${styles.bar}`}
            style={{ width: `${source.healthScore}%` }}
          />
        </div>
      </div>

      {/* Metrics Parameter Grid */}
      <div className="mt-4 grid grid-cols-4 gap-2 border-t border-slate-100 pt-3">
        <div className="rounded-xl bg-slate-50 p-2 text-center border border-slate-100">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">pH</p>
          <p className="mt-0.5 text-xs font-extrabold text-slate-800">{source.pH}</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-2 text-center border border-slate-100">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Turb</p>
          <p className="mt-0.5 text-xs font-extrabold text-slate-800">{source.turbidity}<span className="text-[8px] font-normal text-slate-400"> / 100 index (not NTU)</span></p>
        </div>
        <div className="rounded-xl bg-slate-50 p-2 text-center border border-slate-100">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">TDS</p>
          <p className="mt-0.5 text-xs font-extrabold text-slate-800">{source.tds}</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-2 text-center border border-slate-100">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Temp</p>
          <p className="mt-0.5 text-xs font-extrabold text-slate-800">{source.temperature}°</p>
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-4 flex items-center justify-between text-[11px] font-medium text-slate-400 border-t border-slate-100 pt-2.5">
        <div className="flex items-center gap-1">
          {getTrendIcon()}
          <span className="capitalize">{source.trendDirection} trend</span>
        </div>
        <div className="flex items-center gap-1">
          {source.healthScore >= 60 ? (
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <ShieldAlert className="h-3.5 w-3.5 text-red-500" />
          )}
          <span>{source.updatedTime}</span>
        </div>
      </div>
    </div>
  );
}
