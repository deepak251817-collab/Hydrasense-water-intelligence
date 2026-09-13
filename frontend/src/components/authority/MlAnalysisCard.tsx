import { useEffect, useState } from "react";
import type { ApiError, ReadingAnalysisResponse } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken, clearAuth } from "../../lib/auth";
import MlAnalysisSection, { type MlAnalysisStatus } from "./MlAnalysisSection";

/**
 * Fetches ML analysis for a sensor reading and renders the shared
 * MlAnalysisSection with the correct lifecycle state.
 *
 * State mapping (spec §11):
 * - loading            → in-flight spinner, no fabricated values
 * - 404                → "unavailable" (no reading / no ML result for it)
 * - 401 / 403          → "unauthorized" (RBAC boundary hit; data cleared, no leak)
 * - success + NULL ML  → "unavailable" (pre-ML readings have NULL ML columns)
 * - network / 5xx      → "error"
 *
 * The effect only stores async results; synchronous guard states and the
 * loading state are derived at render time (react-hooks/set-state-in-effect).
 */
export default function MlAnalysisCard({ readingId }: { readingId: number | null }) {
  const [fetched, setFetched] = useState<{
    readingId: number;
    status: MlAnalysisStatus;
    ml: ReadingAnalysisResponse["ml"] | null;
    message: string | null;
    timestamp: string | null;
  } | null>(null);

  useEffect(() => {
    if (readingId === null) return;
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    authorityApi
      .getReadingAnalysis(readingId, token)
      .then((data) => {
        if (cancelled) return;
        // Older readings legitimately have NULL ML columns — treat as unavailable.
        if (!data.ml || data.ml.ml_processed_at === null) {
          setFetched({ readingId, status: "unavailable", ml: null, message: null, timestamp: null });
        } else {
          setFetched({
            readingId,
            status: "success",
            ml: data.ml,
            message: null,
            timestamp: data.timestamp,
          });
        }
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        if (err.statusCode === 404) {
          setFetched({
            readingId,
            status: "unavailable",
            ml: null,
            message: err.detail || "Analysis unavailable for this reading.",
            timestamp: null,
          });
        } else if (err.statusCode === 401 || err.statusCode === 403) {
          // A stale/expired session must not keep authority data around.
          if (err.statusCode === 401) {
            clearAuth();
          }
          setFetched({
            readingId,
            status: "unauthorized",
            ml: null,
            message: "Your account is not authorized to view AI analysis.",
            timestamp: null,
          });
        } else {
          setFetched({
            readingId,
            status: "error",
            ml: null,
            message: err.detail || "Failed to load AI analysis. Please try again later.",
            timestamp: null,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [readingId]);

  // Derived synchronous states — no setState inside the effect body.
  if (readingId === null) {
    return (
      <MlAnalysisSection
        status="unavailable"
        analysis={null}
        message="No reading is available for analysis yet."
        variant="reading"
      />
    );
  }

  const token = getToken();
  if (!token) {
    return (
      <MlAnalysisSection
        status="unauthorized"
        analysis={null}
        message="Sign in with an authority account to view AI analysis."
        variant="reading"
      />
    );
  }

  if (fetched === null || fetched.readingId !== readingId) {
    return <MlAnalysisSection status="loading" analysis={null} variant="reading" />;
  }

  return (
    <MlAnalysisSection
      status={fetched.status}
      analysis={fetched.ml}
      message={fetched.message}
      variant="reading"
      readingTimestamp={fetched.timestamp}
    />
  );
}
