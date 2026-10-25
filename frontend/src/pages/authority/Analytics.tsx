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
            <span>Forecast &amp; Model Status</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Baseline Forecast &amp; Evaluation
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Time-aware baseline forecasts with holdout evaluation — forecast values are shown only when the evaluation supports them.
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

      {/* How the forecast is evaluated — honest methodology, no fabricated numbers */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4.5 w-4.5 text-cyan-600" />
            <h3 className="text-sm font-bold text-slate-900">
              How the forecast is evaluated
            </h3>
          </div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            Ridge baseline • chronological holdout
          </span>
        </div>

        <p className="text-xs leading-relaxed text-slate-600">
          Forecasts come from the backend&apos;s baseline model (Ridge on a time index
          plus the previous reading), trained per parameter and evaluated on a
          chronological holdout — the most recent 20% of stored history — against
          a naive persistence forecast. Forecast values are published only when
          the model&apos;s holdout MAE beats persistence; otherwise the forecast card
          reports &quot;Forecasting unavailable&quot; with the reason. When history is
          too short, the card shows observed-versus-required readiness numbers
          instead of numbers claimed as forecasts.
        </p>
        <p className="text-[11px] text-slate-500 italic">
          SHAP-style feature attribution is not implemented in this project, so
          no attribution percentages are shown. Forecasts are model outputs —
          not measurements, not laboratory results, and not a safety
          certification.
        </p>
      </div>
    </div>
  );
}
