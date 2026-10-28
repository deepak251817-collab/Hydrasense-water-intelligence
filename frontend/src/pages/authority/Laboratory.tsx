import { mockLabRecords } from "../../data/mockData";
import PrototypeBanner from "../../components/authority/PrototypeBanner";
import { FlaskConical, CheckCircle2, Clock, ShieldCheck } from "lucide-react";

export default function Laboratory() {
  return (
    <div className="space-y-6">
      <PrototypeBanner
        feature="Laboratory records"
        missing="Needed to make this real: a lab-results model with sample
        chain-of-custody, uploads of instrument output entered by authorised users, and an
        explicit rule that laboratory values are never derived from the four hardware
        sensors."
      />
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
          <FlaskConical className="h-3.5 w-3.5 text-cyan-700" />
          <span>Statutory Testing Records</span>
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
          Laboratory Verification & Certification
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Benchmark wet-chemistry laboratory assay reports for heavy metals, BOD, COD, and microbiological assays.
        </p>
      </div>

      {/* Lab Records Table */}
      <div className="space-y-4">
        {mockLabRecords.map((record) => (
          <div
            key={record.sampleId}
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs hover:border-slate-300 transition-all space-y-4"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-slate-400">
                    {record.sampleId}
                  </span>
                  <span className="text-slate-300">•</span>
                  <span className="text-xs font-semibold text-slate-500">
                    Collected: {record.collectedAt}
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 mt-0.5">
                  {record.sourceName}
                </h3>
              </div>

              <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${
                record.status === "Certified"
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-amber-50 text-amber-700 border-amber-200"
              }`}>
                {record.status === "Certified" ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <Clock className="h-3.5 w-3.5" />
                )}
                <span>{record.status}</span>
              </span>
            </div>

            {/* Assay Parameters Matrix */}
            <div>
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 block mb-2">
                Certified Wet-Lab Assay Parameters
              </span>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 text-xs">
                <div className="rounded-xl bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-400 font-semibold block text-[10px]">BOD (5-Day)</span>
                  <span className="font-extrabold text-slate-800 mt-0.5 block">{record.parameters.bod}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-400 font-semibold block text-[10px]">COD</span>
                  <span className="font-extrabold text-slate-800 mt-0.5 block">{record.parameters.cod}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-400 font-semibold block text-[10px]">Fecal Coliform</span>
                  <span className="font-extrabold text-slate-800 mt-0.5 block">{record.parameters.fecalColiform}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-400 font-semibold block text-[10px]">Heavy Metals Assay</span>
                  <span className="font-extrabold text-slate-800 mt-0.5 block">{record.parameters.heavyMetals}</span>
                </div>
              </div>
            </div>

            {/* Certifying Authority */}
            <div className="flex items-center justify-between text-xs text-slate-500 border-t border-slate-100 pt-3">
              <div className="flex items-center gap-1.5 font-medium text-slate-600">
                <ShieldCheck className="h-4 w-4 text-cyan-600" />
                <span>Certified By: <strong>{record.certifiedBy}</strong></span>
              </div>
              <span className="text-slate-400">Tested: {record.testedAt}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
