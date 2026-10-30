import { FlaskConical } from "lucide-react";

interface PrototypeBannerProps {
  /** What this page currently shows. */
  feature: string;
  /** Precisely what is still missing before the page can be real. */
  missing: string;
}

/**
 * Honest labelling for authority pages that still render demonstration data.
 * These pages must never imply that the records are genuine operational
 * entries or that laboratory values come from the four hardware sensors.
 */
export default function PrototypeBanner({ feature, missing }: PrototypeBannerProps) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
      <div>
        <p className="text-xs font-bold uppercase tracking-wide text-slate-600">
          Prototype — demonstration data only
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          {feature} are clearly-labelled demonstration records loaded from the frontend
          bundle, not live database records, and nothing shown here is a genuine
          operational record. {missing}
        </p>
      </div>
    </div>
  );
}
