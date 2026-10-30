import { mockWaterSources } from "../../data/mockData";
import WarningBanner from "../../components/public/WarningBanner";
import DemoDataNotice from "../../components/public/DemoDataNotice";
import { BellRing, Info } from "lucide-react";

export default function Warnings() {
  const warningSources = mockWaterSources.filter(
    (s) => s.publicWarning || s.risk === "Critical" || s.risk === "High" || s.risk === "Watch"
  );

  return (
    <div className="mx-auto max-w-5xl py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      <DemoDataNotice>
        Live public warnings are served per station from the backend; these
        demonstration entries are not current advisories and must not be acted on.
      </DemoDataNotice>

      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-900">
          <BellRing className="h-3.5 w-3.5 text-amber-700" />
          <span>Active Public Water Advisories</span>
        </div>
        <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
          Public Ecological Warnings
        </h1>
        <p className="mt-1 text-sm text-slate-500 max-w-2xl leading-relaxed">
          Official environmental and water-quality alerts issued for municipal water bodies based on real-time automated screening and ongoing authority field assessments.
        </p>
      </div>

      {/* Advisory Guidance Alert */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs flex items-start gap-4">
        <div className="rounded-xl bg-cyan-50 p-2.5 text-cyan-700 shrink-0">
          <Info className="h-5 w-5" />
        </div>
        <div className="text-xs text-slate-600 space-y-1">
          <h4 className="font-bold text-slate-900">How to interpret public warnings:</h4>
          <p className="leading-relaxed">
            • <strong className="text-red-600">Critical Warning:</strong> Rapid contamination or severe hypoxia detected. Avoid all recreational, domestic, or culinary usage.
          </p>
          <p className="leading-relaxed">
            • <strong className="text-orange-600">High Advisory:</strong> Predictive models or sensors indicate deteriorating trends. Inflow investigations active.
          </p>
          <p className="leading-relaxed">
            • <strong className="text-amber-600">Watch Notice:</strong> Elevated dissolved solids or slight turbidity shifts under continuous monitoring.
          </p>
        </div>
      </div>

      {/* Warning List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs font-bold text-slate-600 border-b border-slate-200 pb-3">
          <span>Active Advisories ({warningSources.length})</span>
          <span className="text-slate-400 font-normal">Synchronized with Municipal Operations</span>
        </div>

        <WarningBanner sources={mockWaterSources} />
      </div>
    </div>
  );
}
