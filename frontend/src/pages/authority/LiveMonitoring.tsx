import { useEffect, useState } from "react";
import { mockSensorProbes, mockWaterSources } from "../../data/mockData";
import SensorHealth from "../../components/authority/SensorHealth";
import WaterTrendChart from "../../components/authority/WaterTrendChart";
import MlIndicator from "../../components/authority/MlIndicator";
import { useLatestAnalysis } from "../../lib/useLatestAnalysis";
import type { MonitoringStation } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";
import { Radio, Cpu, Brain } from "lucide-react";

export default function LiveMonitoring() {
  const [selectedSourceId, setSelectedSourceId] = useState("source-tg-halli");
  const selectedSource =
    mockWaterSources.find((s) => s.id === selectedSourceId) || mockWaterSources[0];

  // Phase 7: backend stations for real ML indicators. The demo telemetry board
  // above is simulated; the ML indicators below show ONLY backend-returned data.
  const [backendStations, setBackendStations] = useState<MonitoringStation[]>([]);
  const [mlStationCode, setMlStationCode] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    authorityApi
      .getAllStations(token)
      .then((data: MonitoringStation[]) => {
        setBackendStations(data);
        if (data.length > 0) {
          setMlStationCode((current) => current ?? data[0].station_code);
        }
      })
      .catch(() => {
        // Degrade silently: the ML panel renders its "unavailable" state.
      });
  }, []);

  const latest = useLatestAnalysis(mlStationCode);
  const latestML = latest.status === "success" ? latest.data : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
            <Radio className="h-3.5 w-3.5 text-cyan-700 animate-pulse" />
            <span>High-Frequency Telemetry Stream</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Live IoT Sensor Monitoring
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time optical and potentiometric probe array streaming via MQTT Mesh Uplink.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={selectedSourceId}
            onChange={(e) => setSelectedSourceId(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-800 shadow-xs outline-none focus:border-cyan-500"
          >
            {mockWaterSources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name} ({source.type})
              </option>
            ))}
          </select>

          {backendStations.length > 0 && (
            <select
              value={mlStationCode ?? ""}
              onChange={(e) => setMlStationCode(e.target.value)}
              aria-label="Backend station for ML indicators"
              className="rounded-xl border border-cyan-200 bg-cyan-50/50 px-3.5 py-2 text-xs font-bold text-cyan-900 shadow-xs outline-none focus:border-cyan-500"
            >
              {backendStations.map((station) => (
                <option key={station.id} value={station.station_code}>
                  {station.station_code} — {station.station_name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Grid: Charts & Diagnostics */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <WaterTrendChart selectedSource={selectedSource} />

          {/* ML indicators for the latest backend reading (Phase 7) */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <Brain className="h-4.5 w-4.5 text-cyan-600" />
                <h3 className="text-sm font-bold text-slate-900">ML Analysis — Latest Reading</h3>
              </div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2.5 py-0.5">
                Authority only · Backend ML pipeline
              </span>
            </div>
            <div className="mt-4">
              {latest.status === "loading" && (
                <p className="text-sm text-slate-500 animate-pulse" data-testid="ml-live-loading">
                  Loading ML analysis…
                </p>
              )}
              {latest.status === "success" && latestML && (
                <>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500 mb-3">
                    <span>
                      Station: <strong className="text-slate-700">{latestML.station_code}</strong>
                    </span>
                    <span>
                      Reading #{latestML.reading_id} ·{" "}
                      {new Date(latestML.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <MlIndicator
                    anomalyLabel={latestML.ml.anomaly_label}
                    anomalyScore={latestML.ml.anomaly_score}
                    qualityLabel={latestML.ml.water_quality_label}
                  />
                </>
              )}
              {(latest.status === "unavailable" || latest.status === "idle") && (
                <p className="text-sm text-slate-500" data-testid="ml-live-unavailable">
                  {latest.message || "Analysis unavailable — no ML result for this station yet."}{" "}
                  No default classification is assumed.
                </p>
              )}
              {latest.status === "unauthorized" && (
                <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-4" data-testid="ml-live-unauthorized">
                  {latest.message || "AI analysis is restricted to authority accounts."}
                </p>
              )}
              {latest.status === "error" && (
                <p className="text-sm text-red-800 bg-red-50 border border-red-200 rounded-xl p-4" data-testid="ml-live-error">
                  {latest.message || "Failed to load ML analysis."}
                </p>
              )}
            </div>
          </div>

          {/* Real-time Telemetry Packet Feed */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="h-4.5 w-4.5 text-slate-700" />
                <h3 className="text-sm font-bold text-slate-900">
                  MQTT Telemetry Stream (Simulated Node Packets)
                </h3>
              </div>
              <span className="text-[10px] font-mono text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded font-bold">
                STREAM ACTIVE • 5000ms POLLING
              </span>
            </div>

            <div className="mt-4 font-mono text-[11px] bg-slate-950 p-4 rounded-xl text-slate-300 overflow-x-auto max-h-[220px] space-y-2 border border-slate-800">
              <p className="text-emerald-400">[08:30:12.110] [UPLINK] Node_TG_Halli: {"{ ph: 6.91, turb_ntu: 17.62, tds_ppm: 412.0, temp_c: 28.1, do_mgl: 4.9 }"}</p>
              <p className="text-cyan-400">[08:30:17.112] [CRC_OK] Packet 0xFA481 verified (RSSI: -64 dBm, Batt: 89%)</p>
              <p className="text-amber-400">[08:30:22.115] [ANOMALY] Turbidity differential exceeds rate threshold (+0.8 NTU/cycle)</p>
              <p className="text-emerald-400">[08:30:27.118] [UPLINK] Node_TG_Halli: {"{ ph: 6.90, turb_ntu: 17.68, tds_ppm: 414.0, temp_c: 28.2, do_mgl: 4.88 }"}</p>
            </div>
          </div>
        </div>

        <div>
          <SensorHealth probes={mockSensorProbes} />
        </div>
      </div>
    </div>
  );
}
