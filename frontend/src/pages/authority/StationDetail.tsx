import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  mockWaterSources,
  mockAlerts,
  mockIncidents,
  mockInspections,
  mockLabRecords,
  mockSensorProbes,
} from "../../data/mockData";
import {
  ArrowLeft,
  Activity,
  Droplets,
  Thermometer,
  Wind,
  BarChart2,
  Brain,
  ShieldCheck,
  MapPin,
  Bell,
  AlertTriangle,
  ClipboardList,
  FlaskConical,
  Eye,
  ScrollText,
  CheckCircle2,
  Sparkles,
  Info,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import MlLatestCard from "../../components/authority/MlLatestCard";

type Section =
  | "overview"
  | "readings"
  | "analysis"
  | "trends"
  | "ai"
  | "health"
  | "nearby"
  | "alerts"
  | "incidents"
  | "inspections"
  | "lab"
  | "public"
  | "audit";

const SECTIONS: { id: Section; label: string; icon: React.ElementType }[] = [
  { id: "overview",    label: "Overview",          icon: Activity },
  { id: "readings",   label: "Live Readings",      icon: Droplets },
  { id: "analysis",   label: "AI Analysis",         icon: Brain },
  { id: "trends",     label: "Historical Trends",  icon: BarChart2 },
  { id: "ai",         label: "AI Insights (Preview)", icon: Sparkles },
  { id: "health",     label: "Sensor Health",      icon: ShieldCheck },
  { id: "nearby",     label: "Nearby Stations",    icon: MapPin },
  { id: "alerts",     label: "Alerts",             icon: Bell },
  { id: "incidents",  label: "Incidents",          icon: AlertTriangle },
  { id: "inspections",label: "Inspections",        icon: ClipboardList },
  { id: "lab",        label: "Lab Results",        icon: FlaskConical },
  { id: "public",     label: "Public View",        icon: Eye },
  { id: "audit",      label: "Audit History",      icon: ScrollText },
];

function RiskBadge({ risk }: { risk: string }) {
  const cls =
    risk === "Critical" ? "bg-red-100 text-red-700 border-red-200" :
    risk === "High"     ? "bg-orange-100 text-orange-700 border-orange-200" :
    risk === "Watch"    ? "bg-amber-100 text-amber-700 border-amber-200" :
                          "bg-emerald-100 text-emerald-700 border-emerald-200";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-black uppercase tracking-wide ${cls}`}>
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 bg-current"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
      </span>
      {risk}
    </span>
  );
}

export default function StationDetail() {
  const { stationId } = useParams();
  const [activeSection, setActiveSection] = useState<Section>("overview");

  const source = mockWaterSources.find((s) => s.id === stationId);

  if (!source) {
    return (
      <div className="py-20 text-center">
        <h2 className="text-xl font-bold text-slate-900">Station "{stationId}" not found.</h2>
        <Link to="/authority/map" className="mt-4 inline-block text-cyan-600 hover:underline">
          ← Return to Map
        </Link>
      </div>
    );
  }

  const otherSources = mockWaterSources.filter((s) => s.id !== source.id);

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <Link
          to="/authority/map"
          className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Water Intelligence Map
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <p className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">{source.id} · {source.type}</p>
            <h1 className="text-2xl font-bold text-slate-900 mt-1">{source.name}</h1>
            <p className="text-slate-500 text-sm mt-0.5">{source.location}</p>
          </div>
          <div className="flex items-center gap-3">
            <RiskBadge risk={source.risk} />
            <span className="text-xs text-slate-400 font-medium">Updated {source.updatedTime}</span>
          </div>
        </div>
      </div>

      {/* Horizontal Section Nav */}
      <div className="overflow-x-auto">
        <div className="flex gap-1 bg-slate-100 rounded-2xl p-1.5 w-max min-w-full">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveSection(id)}
              className={`flex items-center gap-1.5 whitespace-nowrap px-3 py-2 rounded-xl text-xs font-semibold transition-all ${
                activeSection === id
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Section Content */}
      <div>
        {/* 1. Overview */}
        {activeSection === "overview" && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Health Score",   value: `${source.healthScore}/100`, sub: "Overall",        color: "cyan" },
                { label: "Trend",          value: source.trendDirection,        sub: "Direction",      color: "slate" },
                { label: "Source Type",    value: source.type,                  sub: "Category",       color: "slate" },
                { label: "Public Warning", value: source.publicWarning ? "Active" : "None", sub: "Status", color: source.publicWarning ? "red" : "emerald" },
              ].map(({ label, value, sub, color }) => (
                <div key={label} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
                  <p className={`text-2xl font-extrabold mt-2 capitalize text-${color}-600`}>{value}</p>
                  <p className="text-xs text-slate-400 mt-1">{sub}</p>
                </div>
              ))}
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h2 className="font-bold text-slate-900 mb-3">Station Overview</h2>
              <p className="text-sm text-slate-600 leading-relaxed">
                <strong>{source.name}</strong> ({source.id}) is a <strong>{source.type.toLowerCase()}</strong> monitoring station located at <strong>{source.location}</strong>.
                The station currently reports a risk level of <strong>{source.risk}</strong> with an overall health score of <strong>{source.healthScore}/100</strong>.
                The trend direction is <strong>{source.trendDirection}</strong>. Last telemetry update: <strong>{source.updatedTime}</strong>.
              </p>
              {source.publicWarning && (
                <div className="mt-4 flex gap-3 items-start bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-800">
                  <AlertTriangle className="h-5 w-5 shrink-0 text-red-500" />
                  <p>{source.publicMessage}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 2. Live Readings */}
        {activeSection === "readings" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              {[
                { label: "pH Level",          value: source.pH,              unit: "",       icon: Droplets,     normal: source.pH >= 6.5 && source.pH <= 8.5 },
                { label: "Turbidity",         value: source.turbidity,       unit: " NTU",   icon: Wind,         normal: source.turbidity < 10 },
                { label: "TDS",               value: source.tds,             unit: " mg/L",  icon: Droplets,     normal: source.tds < 400 },
                { label: "Temperature",       value: source.temperature,     unit: "°C",     icon: Thermometer,  normal: source.temperature < 30 },
                { label: "Dissolved O₂",      value: source.dissolvedOxygen, unit: " mg/L",  icon: Activity,     normal: source.dissolvedOxygen > 5 },
              ].map(({ label, value, unit, icon: Icon, normal }) => (
                <div
                  key={label}
                  className={`bg-white rounded-2xl border p-5 shadow-sm ${normal ? "border-slate-200" : "border-red-200 bg-red-50"}`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <Icon className={`h-4 w-4 ${normal ? "text-slate-400" : "text-red-500"}`} />
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</span>
                  </div>
                  <p className={`text-2xl font-extrabold ${normal ? "text-slate-900" : "text-red-700"}`}>
                    {value}{unit}
                  </p>
                  <p className={`text-xs mt-1 font-semibold ${normal ? "text-emerald-600" : "text-red-500"}`}>
                    {normal ? "Within range" : "Out of range"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2b. AI Analysis — real backend ML results (Phase 7) */}
        {activeSection === "analysis" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <MlLatestCard stationCode={stationId ?? null} />
          </div>
        )}

        {/* 3. Historical Trends */}
        {activeSection === "trends" && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h2 className="font-bold text-slate-900 mb-6">pH & Health Score Trend</h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={source.historicalTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" domain={[6, 8]} tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="pH" stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="right" type="monotone" dataKey="healthScore" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h2 className="font-bold text-slate-900 mb-6">Turbidity & TDS Trend</h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={source.historicalTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="turbidity" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} name="Turbidity (NTU)" />
                  <Line type="monotone" dataKey="tds" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} name="TDS (mg/L)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* 4. AI Insights */}
        {activeSection === "ai" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="bg-cyan-50 border border-cyan-100 rounded-2xl p-6 flex gap-4">
              <div className="bg-cyan-100 text-cyan-600 p-3 rounded-xl shrink-0">
                <Sparkles className="h-6 w-6" />
              </div>
              <div>
                <p className="text-xs font-bold text-cyan-800 uppercase tracking-wide mb-1">AI Predictive Insight — Mock UI</p>
                <p className="text-base font-semibold text-cyan-900">{source.aiInsight || "No insight available for this station."}</p>
              </div>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <div className="flex items-start gap-3 text-sm text-slate-500">
                <Info className="h-5 w-5 shrink-0 text-slate-400 mt-0.5" />
                <p>
                  AI Insights below are illustrative preview content only — they are not model
                  outputs. Real machine-learning results (predicted water-quality class and anomaly
                  status from the backend ML pipeline) are shown in the separate "AI Analysis"
                  section. No actual pollution source detection or certified quality determination
                  is made by this module.
                </p>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              {[
                { title: "Trend Prediction (48h)", body: "Turbidity likely to remain elevated based on current gradient. No rainfall forecast to accelerate runoff.", confidence: "Medium" },
                { title: "DO Risk Assessment", body: "Dissolved oxygen at lower threshold. Hypoxic risk elevated if trend continues without intervention.", confidence: "High" },
              ].map(({ title, body, confidence }) => (
                <div key={title} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold text-slate-900 text-sm">{title}</h3>
                    <span className="text-xs bg-slate-100 text-slate-600 font-bold px-2 py-0.5 rounded-full">Confidence: {confidence}</span>
                  </div>
                  <p className="text-sm text-slate-600">{body}</p>
                  <p className="text-xs text-slate-400 mt-3 italic">Mock insight — not a real model output.</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. Sensor Health */}
        {activeSection === "health" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100">
                <h2 className="font-bold text-slate-900">Sensor Probe Status</h2>
              </div>
              <div className="divide-y divide-slate-100">
                {mockSensorProbes.map((probe) => (
                  <div key={probe.id} className="px-6 py-4 flex items-center justify-between gap-4">
                    <div>
                      <p className="font-bold text-slate-900 text-sm">{probe.parameter}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{probe.sensorType}</p>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-right">
                      <span className="text-slate-700 font-semibold">{probe.currentValue}</span>
                      <span className={`px-2.5 py-0.5 rounded-full font-bold ${
                        probe.status === "Healthy" ? "bg-emerald-100 text-emerald-700" :
                        probe.status === "Warning" ? "bg-amber-100 text-amber-700" :
                        "bg-red-100 text-red-700"
                      }`}>{probe.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 6. Nearby Stations */}
        {activeSection === "nearby" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <p className="text-sm text-slate-500">Other monitoring stations on the Arkavathi River corridor.</p>
            {otherSources.map((s) => (
              <div key={s.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-mono font-bold text-slate-400">{s.id}</p>
                  <p className="font-bold text-slate-900">{s.name}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.location}</p>
                </div>
                <div className="flex items-center gap-3">
                  <RiskBadge risk={s.risk} />
                  <Link
                    to={`/authority/stations/${s.id}`}
                    className="text-xs font-bold text-cyan-600 hover:text-cyan-700 whitespace-nowrap"
                  >
                    View →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 7. Alerts */}
        {activeSection === "alerts" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            {mockAlerts.length === 0 ? (
              <p className="text-slate-500 text-sm">No active alerts.</p>
            ) : (
              mockAlerts.map((alert) => (
                <div key={alert.id} className={`bg-white rounded-2xl border p-5 shadow-sm ${
                  alert.severity === "Critical" ? "border-red-200" :
                  alert.severity === "High" ? "border-orange-200" : "border-amber-200"
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-bold text-slate-900 text-sm">{alert.title}</h3>
                    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                      alert.severity === "Critical" ? "bg-red-100 text-red-700" :
                      alert.severity === "High" ? "bg-orange-100 text-orange-700" : "bg-amber-100 text-amber-700"
                    }`}>{alert.severity}</span>
                  </div>
                  <p className="text-sm text-slate-600">{alert.description}</p>
                  <p className="text-xs text-slate-400 mt-2">{alert.timestamp} · {alert.sourceName}</p>
                </div>
              ))
            )}
          </div>
        )}

        {/* 8. Incidents */}
        {activeSection === "incidents" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            {mockIncidents.map((inc) => (
              <div key={inc.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <p className="text-xs font-mono text-slate-400">{inc.id}</p>
                    <h3 className="font-bold text-slate-900 text-sm mt-0.5">{inc.title}</h3>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                      inc.priority === "Critical" ? "bg-red-100 text-red-700" :
                      inc.priority === "High" ? "bg-orange-100 text-orange-700" :
                      inc.priority === "Medium" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"
                    }`}>{inc.priority}</span>
                    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                      inc.status === "Open" ? "bg-red-50 text-red-600" :
                      inc.status === "Investigating" ? "bg-blue-50 text-blue-600" : "bg-emerald-50 text-emerald-600"
                    }`}>{inc.status}</span>
                  </div>
                </div>
                <p className="text-sm text-slate-600">{inc.summary}</p>
                <p className="text-xs text-slate-400 mt-2">{inc.reportedAt} · {inc.assignedTeam}</p>
              </div>
            ))}
          </div>
        )}

        {/* 9. Inspections */}
        {activeSection === "inspections" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            {mockInspections.map((ins) => (
              <div key={ins.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-xs font-mono text-slate-400">{ins.id}</p>
                    <h3 className="font-bold text-slate-900 text-sm mt-0.5">{ins.type}</h3>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                    ins.status === "Completed" ? "bg-emerald-100 text-emerald-700" :
                    ins.status === "Scheduled" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"
                  }`}>{ins.status}</span>
                </div>
                <p className="text-sm text-slate-600">{ins.findings}</p>
                <p className="text-xs text-slate-400 mt-2">{ins.date} · Inspector: {ins.inspector}</p>
              </div>
            ))}
          </div>
        )}

        {/* 10. Lab Results */}
        {activeSection === "lab" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            {mockLabRecords.map((lab) => (
              <div key={lab.sampleId} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-xs font-mono text-slate-400">{lab.sampleId}</p>
                    <h3 className="font-bold text-slate-900 text-sm mt-0.5">{lab.sourceName}</h3>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                    lab.status === "Certified" ? "bg-emerald-100 text-emerald-700" :
                    lab.status === "Pending Lab Analysis" ? "bg-blue-100 text-blue-700" : "bg-red-100 text-red-700"
                  }`}>{lab.status}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
                    <p className="font-semibold text-slate-500 mb-1">BOD</p>
                    <p className="font-bold text-slate-900">{lab.parameters.bod}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
                    <p className="font-semibold text-slate-500 mb-1">COD</p>
                    <p className="font-bold text-slate-900">{lab.parameters.cod}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
                    <p className="font-semibold text-slate-500 mb-1">Fecal Coliform</p>
                    <p className="font-bold text-slate-900">{lab.parameters.fecalColiform}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
                    <p className="font-semibold text-slate-500 mb-1">Heavy Metals</p>
                    <p className="font-bold text-slate-900">{lab.parameters.heavyMetals}</p>
                  </div>
                </div>
                <p className="text-xs text-slate-400 mt-3">Collected: {lab.collectedAt} · Certified by: {lab.certifiedBy}</p>
              </div>
            ))}
          </div>
        )}

        {/* 11. Public View */}
        {activeSection === "public" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-5 flex gap-3 items-start">
              <Eye className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
              <p className="text-sm text-blue-800">
                This section previews what the public-facing QR page shows for this station. Internal incidents, lab details, officer assignments, and AI logs are not exposed.
              </p>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-slate-900">Public Station Card — {source.id}</h2>
                <Link
                  to={`/public/source/${source.id}`}
                  className="text-xs font-bold text-cyan-600 hover:text-cyan-700"
                  target="_blank"
                >
                  Open Public Page →
                </Link>
              </div>
              <div className="border border-slate-200 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-900">{source.name}</span>
                  <RiskBadge risk={source.risk} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <span className="text-slate-500">pH: <strong className="text-slate-800">{source.pH}</strong></span>
                  <span className="text-slate-500">Turbidity: <strong className="text-slate-800">{source.turbidity} NTU</strong></span>
                  <span className="text-slate-500">TDS: <strong className="text-slate-800">{source.tds} ppm</strong></span>
                  <span className="text-slate-500">DO: <strong className="text-slate-800">{source.dissolvedOxygen} mg/L</strong></span>
                </div>
                {source.publicWarning && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-800">
                    <strong>Warning: </strong>{source.publicMessage}
                  </div>
                )}
                <p className="text-xs text-slate-400">✓ Internal incidents hidden · ✓ Officer data hidden · ✓ Lab details hidden</p>
              </div>
            </div>
          </div>
        )}

        {/* 12. Audit History */}
        {activeSection === "audit" && (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100">
                <h2 className="font-bold text-slate-900">Audit Trail</h2>
                <p className="text-xs text-slate-500 mt-0.5">System-generated log of station activity and configuration changes.</p>
              </div>
              <div className="divide-y divide-slate-100">
                {[
                  { time: "Today 09:14", actor: "System", action: `Telemetry sync completed for ${source.id}. 5 parameters updated.` },
                  { time: "Today 08:00", actor: "Alert Engine", action: `Risk status changed to "${source.risk}" based on sensor threshold breach.` },
                  { time: "Yesterday 17:30", actor: "Officer K. Rao", action: "Inspection record INS-4402 attached to station." },
                  { time: "Aug 19, 14:10", actor: "System", action: "Sensor calibration record verified. Probe battery status synced." },
                  { time: "Aug 18, 11:00", actor: "Admin", action: "Station public message updated by authority command center." },
                ].map((entry, i) => (
                  <div key={i} className="px-6 py-4 flex gap-4 items-start">
                    <div className="bg-slate-100 text-slate-500 rounded-lg p-1.5 mt-0.5 shrink-0">
                      <CheckCircle2 className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-sm text-slate-900 font-medium">{entry.action}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{entry.time} · {entry.actor}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
