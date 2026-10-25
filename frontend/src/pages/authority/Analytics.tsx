import { useState } from "react";
import { mockWaterSources } from "../../data/mockData";
import WaterTrendChart from "../../components/authority/WaterTrendChart";
import PredictionCard from "../../components/authority/PredictionCard";
import ModelHealthCard from "../../components/authority/ModelHealthCard";
import { LineChart, Sparkles } from "lucide-react";

export default function Analytics() {
  const [selectedSourceId, setSelectedSourceId] = useState("source-tg-halli");
  const selectedSource =
    mockWaterSources.find((s) => s.id === selectedSourceId) || mockWaterSources[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
            <LineChart className="h-3.5 w-3.5 text-cyan-700" />
            <span>AI Predictive Analytics Engine</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Predictive Analytics & Deterioration Forecast
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Statistical trend projections, time-series anomaly correlation, and AI risk scoring.
          </p>
        </div>

        <select
          value={selectedSourceId}
          onChange={(e) => setSelectedSourceId(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-800 shadow-xs outline-none focus:border-cyan-500"
        >
          {mockWaterSources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.name} ({source.risk} Risk)
            </option>
          ))}
        </select>
      </div>

      {/* Real model health + evaluation metrics (backend /authority/ml/status) */}
      <ModelHealthCard />

      {/* Main Analytics Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <WaterTrendChart selectedSource={selectedSource} />
        </div>
        <div>
          <PredictionCard selectedSource={selectedSource} />
        </div>
      </div>

      {/* Model Parameter Breakdown & SHAP Placeholder */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4.5 w-4.5 text-cyan-600" />
            <h3 className="text-sm font-bold text-slate-900">
              AI Explainability & Feature Contribution Breakdown (SHAP Placeholder)
            </h3>
          </div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            Model: GradientBoost-TimeSeries-v1.4
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Turbidity Surge</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xl font-extrabold text-red-600">+38.4%</span>
              <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded">High Impact</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Strongest driver for predicted water deterioration.</p>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Dissolved Oxygen Depletion</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xl font-extrabold text-orange-600">-24.1%</span>
              <span className="text-[10px] font-bold text-orange-700 bg-orange-100 px-1.5 py-0.5 rounded">Major Impact</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Accelerates biological hypoxic risk rating.</p>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Conductivity / TDS Drift</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xl font-extrabold text-amber-600">+14.2%</span>
              <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">Moderate</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Indicates external runoff and dissolved salts influx.</p>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Temperature Baseline</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xl font-extrabold text-slate-700">+1.2%</span>
              <span className="text-[10px] font-bold text-slate-600 bg-slate-200 px-1.5 py-0.5 rounded">Neutral</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Ambient seasonal temperature within tolerance bands.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
