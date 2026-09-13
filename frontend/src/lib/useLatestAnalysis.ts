import { useEffect, useState } from "react";
import type { ApiError, ReadingAnalysisResponse } from "./api";
import { authorityApi } from "./api";
import { getToken, clearAuth } from "./auth";

export type LatestAnalysisStatus =
  | "idle"
  | "loading"
  | "success"
  | "unavailable"
  | "error"
  | "unauthorized";

export interface LatestAnalysisState {
  status: LatestAnalysisStatus;
  data: ReadingAnalysisResponse | null;
  message: string | null;
}

interface FetchedResult {
  stationCode: string;
  state: Pick<LatestAnalysisState, "status" | "data" | "message">;
}

/**
 * Shared Phase 7 hook: fetches the latest reading + ML analysis for a station
 * (GET /authority/stations/{code}/readings/latest/analysis).
 *
 * State mapping (spec §11):
 * - 404           → "unavailable" (unknown station or no readings yet)
 * - 401 / 403     → "unauthorized" (RBAC boundary; 401 also clears the session)
 * - success + NULL ML columns → "unavailable" (pre-ML readings)
 * - network / 5xx → "error"
 * No fabricated defaults are ever produced.
 *
 * The effect only stores async results; the synchronous guard states (no
 * station / no token) and the loading state are derived at render time, so no
 * setState is ever called synchronously inside the effect
 * (react-hooks/set-state-in-effect).
 */
export function useLatestAnalysis(stationCode: string | null): LatestAnalysisState {
  const [result, setResult] = useState<FetchedResult | null>(null);

  useEffect(() => {
    if (!stationCode) return;
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    authorityApi
      .getLatestStationAnalysis(stationCode, token)
      .then((data) => {
        if (cancelled) return;
        if (!data.ml || data.ml.ml_processed_at === null) {
          setResult({ stationCode, state: { status: "unavailable", data: null, message: null } });
        } else {
          setResult({ stationCode, state: { status: "success", data, message: null } });
        }
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        if (err.statusCode === 404) {
          setResult({
            stationCode,
            state: {
              status: "unavailable",
              data: null,
              message: err.detail || "No reading available for this station yet.",
            },
          });
        } else if (err.statusCode === 401 || err.statusCode === 403) {
          if (err.statusCode === 401) {
            clearAuth();
          }
          setResult({
            stationCode,
            state: {
              status: "unauthorized",
              data: null,
              message: "Your account is not authorized to view AI analysis.",
            },
          });
        } else {
          setResult({
            stationCode,
            state: {
              status: "error",
              data: null,
              message: err.detail || "Failed to load AI analysis. Please try again later.",
            },
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stationCode]);

  // Derived states — no synchronous setState in effects.
  if (!stationCode) {
    return { status: "unavailable", data: null, message: "No station selected." };
  }

  const token = getToken();
  if (!token) {
    return {
      status: "unauthorized",
      data: null,
      message: "Sign in with an authority account to view AI analysis.",
    };
  }

  if (result === null || result.stationCode !== stationCode) {
    // Request in flight, or a stale result for a previously selected station.
    return { status: "loading", data: null, message: null };
  }

  return result.state;
}
