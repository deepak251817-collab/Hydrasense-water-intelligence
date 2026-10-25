/**
 * Model health & evaluation dashboard tests.
 *
 * These pin down the honesty contract of the ModelHealthCard:
 *  - real metrics from the backend report are rendered as-is (never invented);
 *  - a missing evaluation report renders an explicit "not generated" state
 *    with the regeneration command — no placeholder metrics;
 *  - unauthorized, network-error and loading states are handled;
 *  - per-model load badges (Loaded / Not loaded / Missing artifact) reflect
 *    the live inference service state reported by the backend.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { MLStatusResponse } from "../lib/api";

const mockToken = vi.hoisted(() => ({ value: "authority-token" as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return { ...actual, getToken: () => mockToken.value };
});

import ModelHealthCard from "../components/authority/ModelHealthCard";

/** Trimmed but structurally real report — mirrors ml/reports/evaluation_report.json. */
function makeReport(overrides: Partial<MLStatusResponse> = {}): MLStatusResponse {
  return {
    models: [
      {
        key: "isolation_forest",
        name: "Isolation Forest",
        role: "Unsupervised anomaly screening (unusual sensor patterns)",
        file: "isolation_forest.joblib",
        features: ["ph", "turbidity", "tds", "temperature"],
        live_inference: true,
        artifact_present: true,
        loaded: true,
      },
      {
        key: "random_forest",
        name: "Random Forest",
        role: "Safe/Unsafe water-quality classification (predicted class)",
        file: "random_forest_classifier.joblib",
        features: ["pH", "tds", "turbidity", "temperature"],
        live_inference: true,
        artifact_present: true,
        loaded: true,
      },
      {
        key: "xgboost",
        name: "XGBoost",
        role: "Offline deterioration prediction (not connected to live inference)",
        file: "xgboost_deterioration.joblib",
        features: [],
        live_inference: false,
        artifact_present: true,
        loaded: false,
      },
    ],
    evaluation_available: true,
    evaluation: {
      schema_version: "1.0",
      generated_at: "2026-10-23T20:05:56Z",
      generator: "ml/scripts/build_evaluation_report.py",
      honesty_policy: "Every metric is computed from saved artifacts.",
      random_forest: {
        available: true,
        task: "Binary water-quality classification (Safe/Unsafe)",
        live_inference: true,
        dataset: { n_test_samples: 15120 },
        metrics: {
          n_samples: 15120,
          accuracy: 0.9998677,
          balanced_accuracy: 0.9998425,
          f1_macro: 0.9998425,
          roc_auc_unsafe: 0.99999996,
          confusion_matrix: {
            labels: ["Safe", "Unsafe"],
            matrix: [
              [4535, 1],
              [1, 10583],
            ],
            row_semantics: "true class (rows) vs predicted class (columns)",
          },
        },
      },
      isolation_forest: {
        available: true,
        task: "Unsupervised anomaly screening",
        live_inference: true,
        dataset: { n_scored_readings: 9 },
        summary: {
          anomalies_flagged: 4,
          anomaly_rate: 0.4444,
          score_min: -0.0225,
          score_max: 0.1032,
        },
      },
      limitations: [
        "The Safe/Unsafe label is the benchmark dataset's labeling rule; it is not laboratory confirmation.",
        "Isolation Forest has no ground-truth contamination labels; its anomaly rate is descriptive only.",
      ],
    },
    report: "ml/reports/evaluation_report.json",
    generated_at: "2026-10-23T20:05:56Z",
    ...overrides,
  };
}

function mockApi(body: MLStatusResponse | { detail: string }, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
      })
    )
  );
}

beforeEach(() => {
  mockToken.value = "authority-token";
  vi.unstubAllGlobals();
});

describe("ModelHealthCard — model health & evaluation", () => {
  it("renders real evaluation metrics from the backend report", async () => {
    mockApi(makeReport());
    render(<ModelHealthCard />);

    expect(await screen.findByTestId("ml-health-evaluation")).toBeInTheDocument();

    // Random Forest held-out metrics — exact values, no rounding to 100%.
    expect(screen.getByText("99.99%")).toBeInTheDocument(); // accuracy
    expect(screen.getByText("100.00%")).toBeInTheDocument(); // ROC-AUC
    expect(screen.getByText("15120")).toBeInTheDocument(); // test samples

    // Isolation Forest descriptive summary (no accuracy claim).
    expect(screen.getByText("4")).toBeInTheDocument(); // anomalies flagged
    expect(screen.getByText("44.44%")).toBeInTheDocument(); // anomaly rate
    expect(screen.getByText("9")).toBeInTheDocument(); // readings scored

    // Limitations and honesty framing are visible.
    expect(screen.getAllByText(/not laboratory confirmation/).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/not laboratory\s+measurements or guaranteed safety judgments/)
    ).toBeInTheDocument();
  });

  it("shows model load badges that reflect the live service state", async () => {
    mockApi(makeReport());
    render(<ModelHealthCard />);

    const models = await screen.findByTestId("ml-health-models");
    expect(models).toHaveTextContent("Loaded"); // both live models
    expect(models).toHaveTextContent("Not loaded"); // xgboost (offline-only)
    expect(models).toHaveTextContent(/Offline analysis only/);
    expect(models).toHaveTextContent(/features: pH, tds, turbidity, temperature/);
  });

  it("flags a missing artifact explicitly instead of pretending the model is healthy", async () => {
    const report = makeReport();
    report.models[0] = { ...report.models[0], artifact_present: false, loaded: false };
    mockApi(report);
    render(<ModelHealthCard />);

    const models = await screen.findByTestId("ml-health-models");
    expect(models).toHaveTextContent("Missing artifact");
  });

  it("renders an explicit 'not generated' state with the regeneration command", async () => {
    mockApi(
      makeReport({ evaluation_available: false, evaluation: null, report: null, generated_at: null })
    );
    render(<ModelHealthCard />);

    expect(
      await screen.findByTestId("ml-health-no-evaluation")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Evaluation report has not been generated/)
    ).toBeInTheDocument();
    expect(
      screen.getByText("python ml/scripts/build_evaluation_report.py")
    ).toBeInTheDocument();
    // No metric tiles may appear when the report is absent.
    expect(screen.queryByTestId("ml-health-evaluation")).not.toBeInTheDocument();
    expect(screen.queryByText("99.99%")).not.toBeInTheDocument();
  });

  it("shows a loading state until the first response arrives", async () => {
    let release: (() => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve) => {
            release = () =>
              resolve({ ok: true, status: 200, json: async () => makeReport() });
          })
      )
    );
    render(<ModelHealthCard />);

    expect(screen.getByText("Loading model health…")).toBeInTheDocument();

    await waitFor(() => expect(release).toBeDefined());
    release!();
    await waitFor(() =>
      expect(screen.getByTestId("ml-health-evaluation")).toBeInTheDocument()
    );
  });

  it("handles unauthorized access (no token) without calling the API", async () => {
    mockToken.value = null;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ModelHealthCard />);

    expect(
      await screen.findByText(/restricted to authority accounts/)
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("ml-health-evaluation")).not.toBeInTheDocument();
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch")))
    );
    render(<ModelHealthCard />);

    expect(await screen.findByTestId("ml-health-error")).toHaveTextContent(
      /Network error/
    );
    expect(screen.queryByTestId("ml-health-evaluation")).not.toBeInTheDocument();
  });

  it("shows the backend error detail on an HTTP error response", async () => {
    mockApi({ detail: "Could not validate credentials" }, 401);
    render(<ModelHealthCard />);

    expect(await screen.findByTestId("ml-health-error")).toHaveTextContent(
      "Could not validate credentials"
    );
  });

  it("requests the authority ML status endpoint", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => makeReport() })
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ModelHealthCard />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = (
      fetchMock.mock.calls as unknown as Array<
        [RequestInfo | URL, RequestInit | undefined]
      >
    )[0];
    expect(String(url)).toContain("/authority/ml/status");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer authority-token"
    );
  });
});
