/**
 * Floating simulation panel tests.
 *
 * The panel must reuse the existing simulation API (state/start/pause/generate/
 * reset) and the existing forecast endpoint, keep every row labelled simulated,
 * show the SIMULATION MODE banner, and route alerts to an on-screen log only.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  ForecastResponse,
  SimulationState,
  StationAlertsResponse,
} from "../lib/api";

const mockToken = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return {
    ...actual,
    getToken: () => mockToken.value,
  };
});

import SimulationDock from "../components/authority/SimulationDock";

function makeState(overrides: Partial<SimulationState> = {}): SimulationState {
  return {
    running: false,
    station_code: null,
    source_code: null,
    scenario: "normal",
    seed: null,
    interval_seconds: 5,
    step: 0,
    samples_generated: 0,
    started_at: null,
    last_sample_at: null,
    simulated: true,
    label: "SIMULATED DATA — NOT LIVE SENSOR DATA",
    scenarios: [
      "normal",
      "rain_runoff",
      "industrial_discharge",
      "sewage_like",
      "sensor_fault",
    ],
    recent_samples: [],
    ...overrides,
  };
}

function makeForecast(): ForecastResponse {
  return {
    station_code: "ARK-001",
    generated_at: "2026-10-24T10:00:00Z",
    horizon_hours: 12,
    status: "ready",
    unavailable_reason: null,
    message: "Baseline forecast available.",
    data_sources: { simulator: 240 },
    trained_on_simulated: true,
    readiness: {
      min_samples_required: 96,
      min_span_days_required: 7,
      observed_span_days: 12,
      parameters: [
        { parameter: "ph", valid_samples: 240, span_days: 12, sufficient: true },
      ],
    },
    parameters: [
      {
        parameter: "ph",
        label: "pH",
        unit: "pH",
        status: "ready",
        reason: null,
        message: "pH forecast.",
        last_observed: 7.2,
        last_observed_at: "2026-10-24T09:00:00Z",
        model: {
          name: "ridge",
          evaluation: "chronological holdout",
          train_size: 200,
          test_size: 40,
          mae: 0.02,
          rmse: 0.03,
          baseline_mae: 0.05,
          baseline_rmse: 0.06,
        },
        uncertainty: {
          method: "holdout_mae",
          width: 0.02,
          note: "Constant-width holdout MAE band, not a probabilistic interval.",
        },
        points: [
          { timestamp: "2026-10-24T11:00:00Z", value: 7.22, lower: 7.2, upper: 7.24 },
          { timestamp: "2026-10-24T15:00:00Z", value: 7.26, lower: 7.24, upper: 7.28 },
          { timestamp: "2026-10-24T19:00:00Z", value: 7.3, lower: 7.28, upper: 7.32 },
        ],
      },
    ],
  };
}

const simulatedAlerts: StationAlertsResponse = {
  total: 1,
  critical_count: 1,
  warning_count: 0,
  items: [
    {
      parameter: "ph",
      label: "pH",
      value: 9.3,
      unit: "pH",
      severity: "critical",
      title: "Danger level: ph outside the configured screening range",
      message: "pH: 9.3 pH breaches the configured critical level (value > 9.0).",
      reference: "Project configuration",
      next_step: "Confirm with a calibrated meter.",
      timestamp: "2026-10-24T10:00:00Z",
      source: "simulator",
      simulated: true,
      station_code: "ARK-001",
      station_name: "Arkavathi Upstream Station",
    },
  ],
};

function json(body: unknown, ok = true, status = 200) {
  return { ok, status, json: () => Promise.resolve(body) } as Response;
}

function stubFetch(overrides: { start?: SimulationState } = {}) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    if (path.includes("/simulation/state")) return json(makeState());
    if (path.includes("/simulation/start")) {
      return json(
        overrides.start ??
          makeState({
            running: true,
            station_code: "ARK-001",
            source_code: "ARKAVATHI",
            scenario: "industrial_discharge",
            samples_generated: 0,
          })
      );
    }
    if (path.includes("/simulation/pause")) return json(makeState());
    if (path.includes("/simulation/reset")) return json(makeState());
    if (path.includes("/simulation/generate")) return json(makeState());
    if (path.includes("/forecast")) return json(makeForecast());
    if (path.includes("/live-assessment")) {
      return json({
        station_code: "ARK-001",
        assessment: {
          recommendations: {
            recommendations: [
              {
                parameter: "ph",
                label: "pH",
                direction: "above_reference",
                status: "above_permissible",
                value: 9.3,
                unit: "pH",
                reason: "Measured value is above the configured reference.",
                urgency: "high",
                possible_causes: ["Possible alkaline discharge upstream."],
                actions: ["Stop abstraction and check upstream outfalls."],
                avoid: ["Do not use for drinking without treatment."],
              },
            ],
            missing_assessments: [],
            urgency: "high",
            authority_actions: [],
          },
        },
      });
    }
    if (path.includes("/authority/stations")) return json([]);
    if (path.includes("/authority/alerts")) return json(simulatedAlerts);
    return json({ detail: `unhandled ${method} ${path}` }, false, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  mockToken.value = "authority-token";
});

describe("SimulationDock", () => {
  it("opens the panel from the floating button and lists the three rivers and five scenarios", async () => {
    stubFetch();
    render(<SimulationDock />);

    await userEvent.click(screen.getByRole("button", { name: /simulate/i }));

    expect(screen.getAllByText("SIMULATION MODE").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Source")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Arkavathi \(ARK-001\)/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Cauvery \(CAU-001\)/ })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Vrishabhavathi \(VRS-001\)/ })
    ).toBeInTheDocument();

    for (const label of [
      "Normal",
      "Rain runoff (turbidity up)",
      "Industrial discharge (TDS and pH jump)",
      "Sewage-like (TDS up, pH down)",
      "Sensor fault (null readings)",
    ]) {
      expect(screen.getByRole("option", { name: label })).toBeInTheDocument();
    }

    expect(screen.getByRole("button", { name: /start/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pause/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate next batch/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
  });

  it("starts the existing simulation API with the selected station and scenario", async () => {
    const fetchMock = stubFetch();
    render(<SimulationDock />);
    await userEvent.click(screen.getByRole("button", { name: /simulate/i }));

    await userEvent.selectOptions(
      screen.getByLabelText("Scenario"),
      "industrial_discharge"
    );
    await userEvent.click(screen.getByRole("button", { name: /start/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("/simulation/start")
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body).toMatchObject({
        station_code: "ARK-001",
        scenario: "industrial_discharge",
        interval_seconds: 5,
      });
    });

    // The persistent run is now reported as running.
    expect(await screen.findByText("running")).toBeInTheDocument();
  });

  it("shows the SIMULATION MODE banner while the run is active", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        json(
          String(url).includes("/simulation/state")
            ? makeState({ running: true, station_code: "ARK-001" })
            : { detail: "unused" },
          true
        )
      )
    );
    render(<SimulationDock />);

    expect(
      await screen.findByText(/SIMULATION MODE — simulated readings only/i)
    ).toBeInTheDocument();
  });

  it("draws the next hours from the existing forecast endpoint with a labelled uncertainty band", async () => {
    stubFetch();
    render(<SimulationDock />);
    await userEvent.click(screen.getByRole("button", { name: /simulate/i }));

    await userEvent.click(screen.getByRole("button", { name: /show forecast/i }));

    expect(await screen.findByText("Prediction — next 12 h")).toBeInTheDocument();
    expect(screen.getByText("SIMULATED INPUT")).toBeInTheDocument();
    expect(screen.getAllByText("Prediction").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Uncertainty band").length).toBeGreaterThan(0);
    expect(screen.getByTestId("simulation-forecast-chart")).toBeInTheDocument();
    expect(
      screen.getByText(/Constant-width holdout MAE band/i)
    ).toBeInTheDocument();
  });

  it("logs simulated alerts on screen and states that nothing is delivered", async () => {
    stubFetch();
    render(<SimulationDock />);
    await userEvent.click(screen.getByRole("button", { name: /simulate/i }));

    expect(await screen.findByText(/pH: 9.3 pH breaches/i)).toBeInTheDocument();
    expect(
      screen.getByText(/No email, SMS or laboratory message is sent/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Alert log/)).toBeInTheDocument();
    expect(await screen.findByText(/Stop abstraction/i)).toBeInTheDocument();
  });
});
