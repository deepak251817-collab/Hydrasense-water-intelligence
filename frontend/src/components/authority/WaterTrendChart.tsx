import { useState } from "react";
import type { WaterSource } from "../../data/mockData";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { TrendingUp, AlertTriangle } from "lucide-react";

interface WaterTrendChartProps {
  selectedSource: WaterSource;
}

type ParameterKey = "healthScore" | "turbidity" | "tds" | "pH";

interface ParameterConfig {
  key: ParameterKey;
  label: string;
  unit: string;
  color: string;
  gradientId: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
  unit: string;
}

function CustomChartTooltip({ active, payload, label, unit }: TooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-md">
        <p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
          Telemetry Time: {label}
        </p>
        <p className="mt-1 text-sm font-extrabold text-slate-900">
          {payload[0].value}
          <span className="text-xs font-semibold text-slate-500">
            {unit}
          </span>
        </p>
      </div>
    );
  }
  return null;
}

export default function WaterTrendChart({ selectedSource }: WaterTrendChartProps) {
  const [activeParam, setActiveParam] = useState<ParameterKey>("healthScore");

  const parameters: ParameterConfig[] = [
    {
      key: "healthScore",
      label: "Composite Health",
      unit: " / 100",
      color: "#0284c7", // Sky-600
      gradientId: "colorHealth",
    },
    {
      key: "turbidity",
      label: "Turbidity Index (0–100, not NTU)",
      unit: " / 100",
      color: "#06b6d4", // Cyan-500
      gradientId: "colorTurbidity",
    },
    {
      key: "tds",
      label: "TDS",
      unit: " mg/L",
      color: "#6366f1", // Indigo-500
      gradientId: "colorTds",
    },
    {
      key: "pH",
      label: "pH Level",
      unit: "",
      color: "#8b5cf6", // Violet-500
      gradientId: "colorPh",
    },
  ];

  const config = parameters.find((p) => p.key === activeParam) || parameters[0];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs flex flex-col h-full">
      {/* Header & Controls */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-5">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-cyan-50 p-2 text-cyan-600">
            <TrendingUp className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
                Water Quality Telemetry Trend
              </h2>
              {selectedSource.trendDirection === "deteriorating" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 px-2 py-0.5 text-[10px] font-extrabold text-red-700">
                  <AlertTriangle className="h-3 w-3" />
                  Deteriorating State
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 font-medium">
              Node: <span className="font-bold text-slate-700">{selectedSource.name}</span> ({selectedSource.location})
            </p>
          </div>
        </div>

        {/* Tab buttons */}
        <div className="flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1 border border-slate-200/60">
          {parameters.map((param) => (
            <button
              key={param.key}
              type="button"
              onClick={() => setActiveParam(param.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeParam === param.key
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              {param.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="mt-6 flex-1 min-h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={selectedSource.historicalTrend}
            margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id={config.gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={config.color} stopOpacity={0.25} />
                <stop offset="95%" stopColor={config.color} stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis
              dataKey="time"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#64748b", fontSize: 11, fontWeight: 600 }}
              dy={10}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#64748b", fontSize: 11, fontWeight: 600 }}
              dx={-5}
            />
            <Tooltip content={<CustomChartTooltip unit={config.unit} />} />
            <Area
              type="monotone"
              dataKey={config.key}
              stroke={config.color}
              strokeWidth={2.5}
              fillOpacity={1}
              fill={`url(#${config.gradientId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-100 pt-3">
        <span>Displaying last 5 telemetry packet cycles</span>
        <span className="font-semibold text-slate-500">Source: Sensor Mesh Gateway 04</span>
      </div>
    </div>
  );
}
