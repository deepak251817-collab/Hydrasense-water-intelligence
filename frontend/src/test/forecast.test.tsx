/**
 * Forecast card honesty tests.
 *
 * Covers: ready forecast (values + model-vs-baseline metrics + simulated badge),
 * unavailable forecast with readiness numbers, unpublished parameter metrics
 * without forecast points, API failure state, and the fixed "model output, not
 * a measurement" footer.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ForecastResponse } from "../lib/api";
import { mockWaterSources } from "../data/mockData";

const mockToken = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return {
    ...actual,
    getToken: () => mockToken.value,
  };
});

import PredictionCard from "../components/authority/PredictionCard";

const source = mockWaterSources[0]; // Arkavathi River -> ARK-001

function makeForecast(overrides: Partial<ForecastResponse> = {}): ForecastResponse {
  return {
    station_code: "ARK-001",
    generated_at: "2026-10-24T10:00:00Z",
    horizon_hours: 24,
    status: "ready",
    unavailable_reason: null,
    message:
      "Baseline forecast available for 4 of 4 parameters over the next 24 h, after time-aware holdout evaluation against a persistence baseline. Forecasts are model outputs, not measurements or guarantees. Training history includes simulated demo readings — treat this as demonstration output, not real-world evidence.",
    data_sources: { simulator: 300 },
    trained_on_simulated: true,
    readiness: {
      min_samples_required: 96,
      min_span_days_required: 7,
      observed_span_days: 12.4,
      parameters: [
        { parameter: "ph", valid_samples: 300, span_days: 12.4, sufficient: true },
        { parameter: "tds", valid_samples: 300, span_days: 12.4, sufficient: true },
        { parameter: "temperature", valid_samples: 300, span_days: 12.4, sufficient: true },
        { parameter: "turbidity", valid_samples: 300, span_days: 12.4, sufficient: true },
      ],
    },
    parameters: [
      {
        parameter: "ph",
        label: "pH",
        unit: "pH",
        status: "ready",
        reason: null,
        message: "pH forecast over the next 24 h, supported by holdout evaluation. Model outputs, not measurements.",
        last_observed: 7.2,
        last_observed_at: "2026-10-24T09:00:00Z",
        model: {
          name: "ridge (time index + previous reading), recursive",
          evaluation: "chronological train/test split (last 20% held out), one-step-ahead",
          train_size: 239,
          test_size: 60,
          mae: 0.01,
          rmse: 0.013,
          baseline_mae: 0.05,
          baseline_rmse: 0.06,
        },
        uncertainty: {
          method: "holdout_mae",
          width: 0.01,
          note: "± MAE measured on the chronological holdout — a constant-width empirical approximation, not a probabilistic interval.",
        },
        points: [
          { timestamp: "2026-10-24T10:00:00Z", value: 7.21, lower: 7.2, upper: 7.22 },
          { timestamp: "2026-10-25T09:00:00Z", value: 7.3, lower: 7.29, upper: 7.31 },
        ],
      },
      {
        parameter: "tds",
        label: "TDS",
        unit: "mg/L (≈ ppm)",
        status: "unavailable",
        reason: "model_not_better_than_baseline",
        message: "Forecast not published for TDS: holdout MAE did not beat the persistence baseline.",
        last_observed: 310,
        last_observed_at: "2026-10-24T09:00:00Z",
        model: {
          name: "ridge (time index + previous reading), recursive",
          evaluation: "chronological train/test split (last 20% held out), one-step-ahead",
          train_size: 239,
          test_size: 60,
          mae: 40.5,
          rmse: 51.2,
          baseline_mae: 33.1,
          baseline_rmse: 42.0,
        },
        uncertainty: null,
        points: [],
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  mockToken.value = "authority-token";
});

describe("PredictionCard (honest forecast)", () => {
  it("shows supported forecast values with model vs persistence metrics", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeForecast()) })
      )
    );
    render(<PredictionCard selectedSource={source} />);

    await waitFor(() => {
      expect(screen.getByText("Baseline Forecast")).toBeInTheDocument();
    });
    expect(screen.getByText("ARK-001 • Arkavathi River")).toBeInTheDocument();
    // Simulated-history honesty badge (badge + message mention it).
    expect(screen.getAllByText(/simulated demo readings/i).length).toBeGreaterThanOrEqual(1);
    // Forecast label + value for pH (last point 7.30).
    expect(screen.getAllByText("Forecast").length).toBeGreaterThan(0);
    expect(screen.getByText("7.30")).toBeInTheDocument();
    // Model vs persistence comparison is visible.
    expect(screen.getAllByText(/MAE 0\.01 vs persistence 0\.05/).length).toBeGreaterThan(0);
    // Fixed honesty footer.
    expect(screen.getByText(/Model output — not a measurement/)).toBeInTheDocument();
    // No fabricated confidence percentages anywhere.
    expect(screen.queryByText(/% confidence/)).not.toBeInTheDocument();
  });

  it("marks an unsupported parameter as not published, without points", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeForecast()) })
      )
    );
    render(<PredictionCard selectedSource={source} />);

    await waitFor(() => {
      expect(screen.getByText("Not published")).toBeInTheDocument();
    });
    expect(
      screen.getAllByText(/Holdout MAE 40\.5 vs persistence 33\.1/).length
    ).toBeGreaterThan(0);
  });

  it("renders readiness numbers when forecasting is unavailable", async () => {
    const body = makeForecast({
      status: "unavailable",
      unavailable_reason: "insufficient_data",
      message:
        "Forecasting unavailable: insufficient historical data (best parameter has 7 valid samples; 96 samples spanning at least 7 days are required).",
      trained_on_simulated: false,
      parameters: [],
      readiness: {
        min_samples_required: 96,
        min_span_days_required: 7,
        observed_span_days: 12.0,
        parameters: [
          { parameter: "ph", valid_samples: 7, span_days: 12.0, sufficient: false },
          { parameter: "tds", valid_samples: 7, span_days: 12.0, sufficient: false },
        ],
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) }))
    );
    render(<PredictionCard selectedSource={source} />);

    await waitFor(() => {
      expect(screen.getByText("Forecasting unavailable")).toBeInTheDocument();
    });
    expect(screen.getByText(/96 samples spanning at least 7 days/)).toBeInTheDocument();
    expect(screen.getAllByText(/7\/96 pts/)).toHaveLength(2);
    expect(screen.getAllByText("NEEDS DATA").length).toBe(2);
    expect(screen.queryByText("7.30")).not.toBeInTheDocument();
  });

  it("surfaces API errors instead of inventing a result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down")))
    );
    render(<PredictionCard selectedSource={source} />);

    await waitFor(() => {
      expect(screen.getByText("Forecast unavailable")).toBeInTheDocument();
    });
    expect(screen.getByText("network down")).toBeInTheDocument();
    expect(screen.queryByText("7.30")).not.toBeInTheDocument();
  });
});
