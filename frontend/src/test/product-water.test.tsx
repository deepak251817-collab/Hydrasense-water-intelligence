/**
 * Product-user water testing UI contract:
 *  - the assessment is rendered from the API response, with units and status;
 *  - simulated data is explicitly labelled and never shown as live hardware;
 *  - no future prediction is invented when none is configured;
 *  - loading, error and empty states are present;
 *  - the wizard sends the selected source/use and reading mode to the API.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return {
    ...actual,
    getToken: () => "product-token",
    getUser: () => ({
      id: 7,
      email: "product@example.com",
      full_name: "Product User",
      role: "PRODUCT_USER" as const,
    }),
    clearAuth: vi.fn(),
  };
});

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    productApi: {
      ...actual.productApi,
      getTest: vi.fn(),
      getTests: vi.fn(),
      getDeviceStatus: vi.fn(),
      startTest: vi.fn(),
      getOverview: vi.fn(),
    },
  };
});

import { productApi } from "../lib/api";
import type { ProductWaterTest } from "../lib/api";
import TestResult from "../pages/user/TestResult";
import UserHistory from "../pages/user/UserHistory";
import UserCheckWater from "../pages/user/UserCheckWater";

const BASE_ASSESSMENT = {
  criteria_version: "product-screening-2026.10.1",
  intended_use: "drinking" as const,
  intended_use_label: "Drinking",
  reading_mode: "live" as const,
  reading_timestamp: "2026-10-24T10:00:00+00:00",
  readings: {
    ph: {
      parameter: "ph",
      label: "pH",
      value: 7.2,
      unit: "",
      status: "within_range" as const,
      status_label: "Within configured range",
      reference: "BIS IS 10500:2012 (Amd. 4), Table 1: pH 6.5-8.5",
      note: null,
    },
    tds: {
      parameter: "tds",
      label: "TDS",
      value: 410,
      unit: "mg/L",
      status: "within_range" as const,
      status_label: "Within configured range",
      reference: "BIS IS 10500:2012: TDS 500 mg/L acceptable",
      note: "Low TDS does not prove safety.",
    },
    turbidity: {
      parameter: "turbidity",
      label: "Turbidity",
      value: 22,
      unit: "relative index 0-100 (not NTU)",
      status: "not_comparable" as const,
      status_label: "Not comparable to a standard",
      reference: "No validated NTU calibration available",
      note: "Relative turbidity index - NTU calibration required.",
    },
    temperature: {
      parameter: "temperature",
      label: "Temperature",
      value: 26.5,
      unit: "C",
      status: "informational" as const,
      status_label: "Context only",
      reference: "No temperature limit configured",
      note: "Temperature alone does not establish drinking-water safety.",
    },
  },
  overall: {
    status: "WITHIN_PROJECT_TARGETS" as const,
    label: "Within project screening targets",
    summary:
      "No monitored concern was detected by this screening. This result does not certify that the water is safe to drink.",
    reasons: ["pH 7.2 is within the configured reference range."],
    reason_details: [],
  },
  attention: [
    {
      parameter: "turbidity",
      label: "Turbidity",
      value: 22,
      unit: "relative index 0-100 (not NTU)",
      status: "not_comparable" as const,
      status_label: "Not comparable to a standard",
      message: "Relative turbidity index - NTU calibration required.",
    },
  ],
  suitability: {
    use: "drinking" as const,
    use_label: "Drinking",
    description: "Potable use, compared only against the monitored BIS screening values.",
    standard_code: "BIS-IS-10500:2012",
    standard: "BIS IS 10500:2012 Drinking Water - Specification (Amd. 4), India",
    criteria_version: "product-screening-2026.10.1",
    result: "WITHIN_PROJECT_TARGETS" as const,
    result_label: "Within project screening targets",
    summary:
      "No monitored parameter exceeded the configured drinking-water screening thresholds. Laboratory testing is required to confirm potability.",
    criteria_available: true,
    criteria: [],
    limitations: ["Microbiological and unmeasured chemical contaminants cannot be excluded."],
  },
  data_quality: {
    demo_mode: false,
    reading_mode: "live" as const,
    freshness: "fresh" as const,
    age_seconds: 20,
    calibration_status: "provisional" as const,
    calibration_verified: false,
    stability: null,
    errors: [],
    warnings: ["Device reports uncalibrated or provisional sensors."],
  },
  next_steps: ["Laboratory testing is required to confirm potability."],
  prediction: {
    available: false,
    message: "Future prediction unavailable - forecasting model not configured.",
    model_version: null,
    horizon_minutes: null,
  },
};

function makeTest(overrides: Partial<ProductWaterTest> = {}): ProductWaterTest {
  return {
    id: 1,
    test_code: "WT-000001",
    water_source: "tap",
    water_source_label: "Tap water",
    intended_use: "drinking",
    intended_use_label: "Drinking",
    reading_mode: "live",
    reading_source: "esp32",
    device_id: "ESP32-API-0001",
    device_name: "HydraSense Personal Tester",
    ph: 7.2,
    tds: 410,
    turbidity: 22,
    turbidity_unit: "relative_index_0_100",
    temperature: 26.5,
    reading_timestamp: "2026-10-24T10:00:00+00:00",
    created_at: "2026-10-24T10:00:05+00:00",
    overall_status: "WITHIN_PROJECT_TARGETS",
    overall_label: "Within project screening targets",
    criteria_version: "product-screening-2026.10.1",
    assessment: BASE_ASSESSMENT,
    ...overrides,
  };
}

function renderResult() {
  return render(
    <MemoryRouter initialEntries={["/user/tests/1"]}>
      <Routes>
        <Route path="/user/tests/:testId" element={<TestResult />} />
        <Route path="/user/history" element={<div>history page</div>} />
        <Route path="/user/check-water" element={<div>new test page</div>} />
        <Route path="/user/dashboard" element={<div>dashboard page</div>} />
        <Route path="/user/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productApi.getTests).mockResolvedValue({ total: 0, items: [] });
});

describe("Water assessment result page", () => {
  it("renders the API readings with units and the screening result", async () => {
    vi.mocked(productApi.getTest).mockResolvedValue(makeTest());

    renderResult();

    expect(screen.getByText("Loading water assessment…")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: /water quality assessment/i })
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Within project screening targets").length
    ).toBeGreaterThan(0);
    expect(screen.getByText("410")).toBeInTheDocument();
    expect(screen.getByText("mg/L")).toBeInTheDocument();
    expect(screen.getByText("26.5")).toBeInTheDocument();
    expect(screen.getAllByText(/relative turbidity index/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/not a laboratory safety certification/i)).toBeInTheDocument();
    expect(screen.getAllByText(/laboratory testing is required/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/future prediction unavailable/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/future prediction available/i)).not.toBeInTheDocument();
    expect(screen.getByText(/tap water/i)).toBeInTheDocument();
    expect(screen.getByText(/live hardware reading/i)).toBeInTheDocument();
  });

  it("labels simulated readings and never implies real sensor data", async () => {
    vi.mocked(productApi.getTest).mockResolvedValue(
      makeTest({
        reading_mode: "demo",
        reading_source: "simulated",
        assessment: {
          ...BASE_ASSESSMENT,
          reading_mode: "demo",
          data_quality: {
            ...BASE_ASSESSMENT.data_quality,
            demo_mode: true,
            reading_mode: "demo",
            freshness: "simulated",
            calibration_status: "simulated",
            warnings: ["Simulated readings - not captured from a physical sensor."],
          },
        },
      })
    );

    renderResult();

    expect(
      await screen.findByText(/simulated readings — not real sensor data/i)
    ).toBeInTheDocument();
    expect(screen.getAllByText(/simulated data/i).length).toBeGreaterThan(0);
  });

  it("renders rule-based advice from the backend", async () => {
    vi.mocked(productApi.getTest).mockResolvedValue(
      makeTest({
        assessment: {
          ...BASE_ASSESSMENT,
          recommendations: {
            recommendations: [
              {
                parameter: "tds",
                label: "Total dissolved solids",
                direction: "above",
                status: "above_acceptable",
                value: 2400,
                unit: "mg/L",
                reason: "Above the configured screening range.",
                urgency: "high",
                possible_causes: ["Possible upstream discharge — not confirmed by this reading."],
                actions: [
                  "Re-sample and repeat the TDS measurement before acting on it.",
                  "Arrange laboratory confirmation before relying on this water: these four sensors cannot confirm that the water is safe.",
                ],
                avoid: ["Avoid relying on this water until the reading is re-confirmed."],
              },
            ],
            missing_assessments: [
              "Microbiological indicators and chemical contaminants beyond pH, TDS, " +
                "temperature and turbidity are not measured by these sensors — " +
                "they require laboratory testing.",
            ],
            urgency: "high",
            authority_actions: [],
          },
        },
      })
    );

    renderResult();

    const block = await screen.findByTestId("assessment-recommendations");
    expect(block).toHaveTextContent("high urgency");
    expect(screen.getByTestId("user-recommendation-tds")).toHaveTextContent(
      "Re-sample and repeat the TDS measurement"
    );
    expect(block).toHaveTextContent("cannot confirm that the water is safe");
    expect(block).toHaveTextContent("not measured by these sensors");
    // Incident steps belong to the authority view only.
    expect(screen.queryByTestId("authority-actions")).not.toBeInTheDocument();
  });

  it("omits the advice block when the backend returns an empty set", async () => {
    vi.mocked(productApi.getTest).mockResolvedValue(
      makeTest({
        assessment: {
          ...BASE_ASSESSMENT,
          recommendations: {
            recommendations: [],
            missing_assessments: [],
            urgency: null,
            authority_actions: [],
          },
        },
      })
    );

    renderResult();

    await screen.findByRole("heading", { name: /water quality assessment/i });
    expect(screen.queryByTestId("assessment-recommendations")).not.toBeInTheDocument();
  });

  it("shows a retry state when the assessment cannot be loaded", async () => {
    vi.mocked(productApi.getTest).mockRejectedValue({
      detail: "Unable to load this water assessment.",
      statusCode: 500,
    });

    renderResult();

    expect(await screen.findByText(/assessment unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("Unable to load this water assessment.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("History empty state", () => {
  it("shows an actionable empty state with no fake rows", async () => {
    render(
      <MemoryRouter initialEntries={["/user/history"]}>
        <Routes>
          <Route path="/user/history" element={<UserHistory />} />
          <Route path="/user/login" element={<div>login page</div>} />
          <Route path="/user/check-water" element={<div>new test page</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText(/no water tests yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/kitchen tap/i)).not.toBeInTheDocument();
    expect(productApi.getTests).toHaveBeenCalled();
  });
});

describe("Test wizard", () => {
  it("sends the selected source, intended use and live mode to the API", async () => {
    const user = userEvent.setup();
    vi.mocked(productApi.getDeviceStatus).mockResolvedValue({
      device_id: "ESP32-API-0001",
      device_name: "HydraSense Personal Tester",
      product_code: "HS-API-0001",
      status: "ACTIVE",
      connected: true,
      last_seen: "2026-10-24T10:00:00+00:00",
      reading_age_seconds: 12,
      reading: {
        ph: 7.2,
        tds: 410,
        turbidity: 22,
        turbidity_unit: "relative_index_0_100",
        turbidity_status: "CLEARER",
        temperature: 26.5,
        timestamp: "2026-10-24T10:00:00+00:00",
        source: "esp32",
        calibration: { ph: "pending" },
      },
      note: "Connected - last reading 12 s ago.",
    });
    vi.mocked(productApi.startTest).mockResolvedValue(makeTest({ id: 42 }));

    render(
      <MemoryRouter initialEntries={["/user/check-water"]}>
        <Routes>
          <Route path="/user/check-water" element={<UserCheckWater />} />
          <Route path="/user/tests/:testId" element={<div>result page</div>} />
          <Route path="/user/activate" element={<div>activate page</div>} />
          <Route path="/user/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: /tap water/i }));
    await user.click(screen.getByRole("button", { name: /^drinking/i }));

    expect(await screen.findByText(/device connected/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /run live water test/i }));

    await waitFor(() =>
      expect(productApi.startTest).toHaveBeenCalledWith(
        { water_source: "tap", intended_use: "drinking", reading_mode: "live" },
        "product-token"
      )
    );
    expect(await screen.findByText("result page")).toBeInTheDocument();
  });
});
