import { mockIncidents } from "../../data/mockData";
import PrototypeBanner from "../../components/authority/PrototypeBanner";
import { Flame, Clock, Users } from "lucide-react";

export default function Incidents() {
  const getPriorityStyle = (priority: string) => {
    switch (priority) {
      case "Critical":
        return "bg-red-50 text-red-700 border-red-200";
      case "High":
        return "bg-orange-50 text-orange-700 border-orange-200";
      case "Medium":
        return "bg-amber-50 text-amber-700 border-amber-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  const getStatusStyle = (status: string) => {
    switch (status) {
      case "Investigating":
        return "bg-cyan-50 text-cyan-800 border-cyan-200";
      case "Open":
        return "bg-amber-50 text-amber-800 border-amber-200";
      case "Resolved":
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
      default:
        return "bg-slate-50 text-slate-800 border-slate-200";
    }
  };

  return (
    <div className="space-y-6">
      <PrototypeBanner
        feature="Incidents"
        missing="The backend incident workflow is implemented and tested (AUTHORITY-only
        create/list/detail endpoints, forward-only status transitions with an audit trail,
        lab contacts, verbatim lab results and a generated PDF report). This page still
        needs to be wired to those endpoints, with loading, empty, error and unauthorized
        states, before it can replace the demonstration records."
      />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-orange-50 px-2.5 py-1 text-xs font-bold text-orange-800 border border-orange-200">
            <Flame className="h-3.5 w-3.5 text-orange-600" />
            <span>Active Environmental Incidents</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Water Quality Incident Management
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Operational log of elevated parameter anomalies, rapid response tasks, and containment audits.
          </p>
        </div>
      </div>

      {/* Incidents Table / Cards */}
      <div className="space-y-4">
        {mockIncidents.map((incident) => (
          <div
            key={incident.id}
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs hover:border-slate-300 transition-all space-y-4"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-bold text-slate-400">
                  {incident.id}
                </span>
                <h3 className="text-base font-bold text-slate-900">
                  {incident.title}
                </h3>
              </div>

              <div className="flex items-center gap-2">
                <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${getPriorityStyle(incident.priority)}`}>
                  {incident.priority} Priority
                </span>
                <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getStatusStyle(incident.status)}`}>
                  {incident.status}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed font-medium">
              {incident.summary}
            </p>

            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-1.5 font-semibold text-slate-700">
                  <Users className="h-3.5 w-3.5 text-cyan-600" />
                  <span>{incident.assignedTeam}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-400">
                  <Clock className="h-3.5 w-3.5" />
                  <span>Reported: {incident.reportedAt}</span>
                </div>
              </div>

              <div className="text-slate-500 font-semibold">
                Location: <span className="text-slate-800 font-bold">{incident.sourceName}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
