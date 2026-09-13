import { useLatestAnalysis } from "../../lib/useLatestAnalysis";
import MlAnalysisSection from "./MlAnalysisSection";

/**
 * Fetches the latest reading + ML analysis for a station via the shared
 * useLatestAnalysis hook and renders the shared MlAnalysisSection.
 */
export default function MlLatestCard({ stationCode }: { stationCode: string | null }) {
  const { status, data, message } = useLatestAnalysis(stationCode);

  return (
    <MlAnalysisSection
      status={status}
      analysis={data?.ml ?? null}
      message={message}
      variant="latest"
      readingTimestamp={data?.timestamp ?? null}
    />
  );
}
