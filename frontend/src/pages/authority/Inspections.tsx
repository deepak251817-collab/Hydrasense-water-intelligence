import { mockInspections } from "../../data/mockData";
import PrototypeBanner from "../../components/authority/PrototypeBanner";
import { ClipboardCheck, Calendar, UserCheck } from "lucide-react";

export default function Inspections() {
  return (
    <div className="space-y-6">
      <PrototypeBanner
        feature="Inspections"
        missing="Needed to make this real: an inspections model with scheduling and
        officer-assignment endpoints (AUTHORITY-only writes), status transitions, and
        field-captured results attached to a monitoring station."
      />
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
          <ClipboardCheck className="h-3.5 w-3.5 text-cyan-700" />
          <span>Surveillance & Field Audits</span>
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
          Field Inspection Registry
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Schedule and records of field officer site visits, physical grab sampling, and sensor probe calibrations.
        </p>
      </div>

      {/* Inspections Grid */}
      <div className="space-y-4">
        {mockInspections.map((insp) => (
          <div
            key={insp.id}
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs hover:border-slate-300 transition-all space-y-3"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-xs font-bold text-cyan-700 bg-cyan-50 px-2 py-0.5 rounded">
                  {insp.id}
                </span>
                <h3 className="text-base font-bold text-slate-900">
                  {insp.sourceName}
                </h3>
              </div>

              <div className="flex items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[10px] font-bold text-slate-700">
                  {insp.type}
                </span>
                <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${
                  insp.status === "Completed" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  insp.status === "Scheduled" ? "bg-cyan-50 text-cyan-700 border-cyan-200" : "bg-amber-50 text-amber-700 border-amber-200"
                }`}>
                  {insp.status}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed font-medium">
              <strong className="text-slate-800 font-bold">Field Findings:</strong> {insp.findings}
            </p>

            <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 border-t border-slate-100 pt-3">
              <div className="flex items-center gap-1.5 font-semibold text-slate-700">
                <UserCheck className="h-3.5 w-3.5 text-cyan-600" />
                <span>Inspector: {insp.inspector}</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <Calendar className="h-3.5 w-3.5" />
                <span>Date: {insp.date}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
