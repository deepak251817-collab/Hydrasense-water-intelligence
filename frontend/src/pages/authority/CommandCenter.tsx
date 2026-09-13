import { useEffect, useState } from "react";
import { 
  mockWaterSources, 
  mockAlerts, 
  mockSensorProbes 
} from "../../data/mockData";
import type { Alert } from "../../data/mockData";
import StatCard from "../../components/authority/StatCard";
import WaterSourceCard from "../../components/authority/WaterSourceCard";
import WaterTrendChart from "../../components/authority/WaterTrendChart";
import PredictionCard from "../../components/authority/PredictionCard";
import AlertPanel from "../../components/authority/AlertPanel";
import SensorHealth from "../../components/authority/SensorHealth";
import MlSummaryCard from "../../components/authority/MlSummaryCard";
import type { MonitoringStation } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";
import { 
  Droplets, 
  ShieldAlert, 
  AlertTriangle, 
  Radio 
} from "lucide-react";

export default function CommandCenter() {
  const [selectedSourceId, setSelectedSourceId] = useState<string>("source-tg-halli");
  const [alerts, setAlerts] = useState<Alert[]>(mockAlerts);

  const selectedSource =
    mockWaterSources.find((s) => s.id === selectedSourceId) || mockWaterSources[0];

  const handleAcknowledgeAlert = (id: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, acknowledged: true } : a))
    );
  };

  const handleInspectSource = (sourceId: string) => {
    setSelectedSourceId(sourceId);
  };

  const activeAlertsCount = alerts.filter((a) => !a.acknowledged).length;
  const criticalSourcesCount = mockWaterSources.filter((s) => s.risk === "Critical").length;

  // Phase 7: ML summary uses ONLY backend station data (no fabricated aggregates).
  const [backendStations, setBackendStations] = useState<MonitoringStation[]>([]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    authorityApi
      .getAllStations(token)
      .then((data: MonitoringStation[]) => setBackendStations(data))
      .catch(() => {
        // Degrade gracefully: the ML summary renders its own empty state.
      });
  }, []);

  return (
    <div className="space-y-6">
      {/* Operations Header Banner */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-3xl bg-slate-900 px-6 py-6 text-white shadow-md border border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/20 px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-cyan-300 border border-cyan-500/30">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
              Live Telemetry Mesh
            </span>
            <span className="text-xs text-slate-400 font-medium">
              Last Sync: Today, 08:30:15 IST
            </span>
          </div>

          <h1 className="mt-2 text-xl sm:text-2xl font-bold tracking-tight text-white">
            Good morning, Operator.
          </h1>
          <p className="mt-1 text-xs text-slate-400 max-w-xl">
            Real-time aquatic surveillance active across 5 municipal telemetry nodes. Automated anomaly detection and predictive deterioration flags engaged.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start sm:self-center">
          <div className="rounded-2xl bg-slate-800/80 px-4 py-3 border border-slate-700/60 text-right">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Active Focus
            </span>
            <span className="text-xs font-black text-cyan-400 mt-0.5 block">
              {selectedSource.name}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Monitored Sources"
          value="5"
          icon={Droplets}
          subtext="5 Active IoT node clusters"
          accentColor="cyan"
        />
        <StatCard
          title="Active Alerts"
          value={activeAlertsCount}
          icon={ShieldAlert}
          subtext="Requires operator acknowledgment"
          trend={
            activeAlertsCount > 0
              ? { type: "critical", label: `${activeAlertsCount} Unacknowledged` }
              : { type: "positive", label: "Nominal" }
          }
          accentColor={activeAlertsCount > 0 ? "red" : "emerald"}
        />
        <StatCard
          title="Critical Sources"
          value={criticalSourcesCount}
          icon={AlertTriangle}
          subtext="Severe hypoxia or turbidity spike"
          trend={{ type: "critical", label: "Pond 04 Active" }}
          accentColor="orange"
        />
        <StatCard
          title="Sensor Availability"
          value="98.6%"
          icon={Radio}
          subtext="Uptime average across probes"
          trend={{ type: "positive", label: "+0.4% baseline" }}
          accentColor="emerald"
        />
      </div>

      {/* ML Analysis Summary (backend data only — Phase 7) */}
      <MlSummaryCard stations={backendStations} />

      {/* Analytics & Prediction Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <WaterTrendChart selectedSource={selectedSource} />
        </div>
        <div>
          <PredictionCard selectedSource={selectedSource} />
        </div>
      </div>

      {/* Alerts & Sensor Diagnostics Grid */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <AlertPanel
          alerts={alerts}
          onAcknowledge={handleAcknowledgeAlert}
          onInspect={handleInspectSource}
        />
        <SensorHealth probes={mockSensorProbes} />
      </div>

      {/* Water Sources Directory & Selector */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900 tracking-tight">
              Monitored Water Sources Directory
            </h3>
            <p className="text-xs text-slate-500">
              Click any source card to update telemetry graphs and predictive indicators above.
            </p>
          </div>
          <span className="text-xs font-semibold text-cyan-700 bg-cyan-50 px-2.5 py-1 rounded-lg border border-cyan-200">
            Selected: {selectedSource.name}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {mockWaterSources.map((source) => (
            <WaterSourceCard
              key={source.id}
              source={source}
              isSelected={source.id === selectedSourceId}
              onClick={() => setSelectedSourceId(source.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
