import { Info } from "lucide-react";

/**
 * Honest labelling for public pages that still render frontend-only
 * demonstration content. It must be shown on any page whose values are not
 * loaded from the backend.
 */
export default function DemoDataNotice({ children }: { children?: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-2xl border border-dashed border-amber-300 bg-amber-50 p-3.5 text-[11px] leading-relaxed text-amber-900">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
      <p>
        <strong className="font-bold">Demonstration content.</strong> Values on
        this page come from the frontend demo bundle, not from stored sensor
        readings or a backend assessment.
        {children ? <> {children}</> : null}
      </p>
    </div>
  );
}
