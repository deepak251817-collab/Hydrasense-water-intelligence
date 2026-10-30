import { Link } from "react-router-dom";
import { History, CheckCircle2, ShieldAlert, ArrowRight, RotateCcw } from "lucide-react";

export default function MyChecks() {
  /**
   * Demonstration entries only. The public (unauthenticated) check flow has no
   * backend storage yet, so these are clearly-labelled samples scoped to the
   * three demonstration rivers — never presented as stored readings, and never
   * quoted in NTU (the hardware reports a relative turbidity index 0–100).
   */
  const demoSavedChecks = [
    {
      id: "demo-001",
      sourceName: "Vrishabhavathi River",
      intendedUse: "Domestic Use",
      screeningResult: "Review before regular use",
      status: "Restricted",
      date: "Sample entry",
      details:
        "Sample record: turbidity index 68/100 (CLOUDIER band, higher = cloudier — not NTU), pH 7.4. Demonstration data, not a stored measurement.",
    },
    {
      id: "demo-002",
      sourceName: "Arkavathi River",
      intendedUse: "Drinking",
      screeningResult: "Additional testing required",
      status: "Restricted",
      date: "Sample entry",
      details:
        "Sample record: relative turbidity index — NTU calibration required, so no NTU comparison is made. Demonstration data, not a stored measurement.",
    },
    {
      id: "demo-003",
      sourceName: "Cauvery River",
      intendedUse: "Irrigation",
      screeningResult: "Measured indicators within configured ranges (demo)",
      status: "Demo pass",
      date: "Sample entry",
      details:
        "Sample record: TDS 348 mg/L against the project-configured screening reference. Demonstration data — screening is not a certification of fitness for irrigation.",
    },
  ];

  return (
    <div className="mx-auto max-w-5xl py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-cyan-100 px-3 py-1 text-xs font-bold text-cyan-800">
            <History className="h-3.5 w-3.5 text-cyan-700" />
            <span>Citizen History</span>
          </div>
          <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
            My Water Checks
          </h1>
          <p className="mt-1 text-sm text-slate-500 max-w-2xl">
            Review past water screening checks performed on this device.
          </p>
          <p className="mt-2 inline-flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] font-semibold text-amber-800">
            Demonstration entries — the public check flow does not persist history yet. These
            samples use the three demonstration rivers and show a relative turbidity index
            (0–100), never NTU.
          </p>
        </div>

        <Link
          to="/public/check-water"
          className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-cyan-500 shadow-xs transition-colors self-start"
        >
          <RotateCcw className="h-4 w-4" />
          <span>New Water Check</span>
        </Link>
      </div>

      {/* Checks List */}
      <div className="space-y-4">
        {demoSavedChecks.map((check) => {
          const passed = check.status === "Demo pass";
          return (
            <div
              key={check.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs hover:border-slate-300 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-cyan-700 uppercase tracking-wider">
                      {check.intendedUse}
                    </span>
                    <span className="text-slate-300">•</span>
                    <span className="text-xs text-slate-400 font-medium">{check.date}</span>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 mt-0.5">
                    {check.sourceName}
                  </h3>
                </div>

                <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold self-start ${
                  passed
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-amber-50 text-amber-700 border border-amber-200"
                }`}>
                  {passed ? <CheckCircle2 className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
                  <span>{check.screeningResult}</span>
                </span>
              </div>

              <p className="mt-3 text-xs text-slate-600 leading-relaxed">
                {check.details}
              </p>

              <div className="mt-4 flex items-center justify-between text-[11px] text-slate-400 pt-2">
                <span>Screening reference ID: {check.id}</span>
                <Link
                  to="/public/check-water"
                  className="inline-flex items-center gap-1 text-cyan-700 font-semibold hover:underline"
                >
                  <span>Re-screen this source</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
