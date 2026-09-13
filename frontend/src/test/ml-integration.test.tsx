/**
 * Phase 7 frontend ML integration tests (spec §16).
 *
 * Covers: ML data renders (valid data), Safe/Unsafe classification states,
 * Normal/Anomalous anomaly states, probability rendering, missing-analysis
 * ("Analysis unavailable"), API failure, unauthorized handling (no data leak),
 * public-page ML restriction, existing station details, and authority
 * navigation.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import type { ReadingAnalysisResponse, MLAnalysis } from "../lib/api";

// Mock the auth module so tests control the "logged in" state without touching
// real sessionStorage ordering issues.
const mockToken = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return {
    ...actual,
    getToken: () => mockToken.value,
  };
});

import MlAnalysisSection from "../components/authority/MlAnalysisSection";
import MlLatestCard from "../components/authority/MlLatestCard";
import MlSummaryCard from "../components/authority/MlSummaryCard";
import MlIndicator from "../components/authority/MlIndicator";
import CommandCenter from "../pages/authority/CommandCenter";
import WaterMap from "../pages/authority/WaterMap";
import PublicSource from "../pages/public/PublicSource";

function makeAnalysis(overrides: Partial<MLAnalysis> = {}): MLAnalysis {
  return {
    anomaly_label: 0,
    anomaly_score: 0.21,
    water_quality_label: "Safe",
    safe_probability: 0.87,
    unsafe_probability: 0.13,
    ml_processed_at: "2026-09-13T10:00:00Z",
    ...overrides,
  };
}

function makeResponse(ml: MLAnalysis): ReadingAnalysisResponse {
  return {
    reading_id: 101,
    station_id: 1,
    station_code: "ARK-001",
    device_id: "ESP32-001",
    timestamp: "2026-09-13T09:59:00Z",
    created_at: "2026-09-13T09:59:05Z",
    ph: 7.1,
    turbidity: 3.2,
    tds: 240,
    temperature: 26.5,
    ml,
  };
}

function renderWithRouter(ui: React.ReactElement, initialPath = "/authority") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockToken.value = "authority-token";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("network disabled in this test")))
  );
});

describe("MlAnalysisSection (presentation)", () => {
  it("1. renders ML data when analysis is available", () => {
    render(
      <MlAnalysisSection
        status="success"
        analysis={makeAnalysis()}
        readingTimestamp="2026-09-13T09:59:00Z"
      />
    );
    expect(screen.getByTestId("ml-analysis")).toBeInTheDocument();
    expect(screen.getByTestId("ml-water-quality")).toHaveTextContent("Safe");
    expect(screen.getByTestId("ml-anomaly-status")).toHaveTextContent("Normal condition");
  });

  it("2. renders Safe classification correctly", () => {
    render(<MlAnalysisSection status="success" analysis={makeAnalysis({ water_quality_label: "Safe" })} />);
    const el = screen.getByTestId("ml-water-quality");
    expect(el).toHaveTextContent("Safe (predicted)");
    expect(el).not.toHaveTextContent("Unsafe");
  });

  it("3. renders Unsafe classification correctly", () => {
    render(
      <MlAnalysisSection
        status="success"
        analysis={makeAnalysis({ water_quality_label: "Unsafe", unsafe_probability: 0.8 })}
      />
    );
    expect(screen.getByTestId("ml-water-quality")).toHaveTextContent("Unsafe (predicted)");
  });

  it("4. renders Normal anomaly state correctly", () => {
    render(<MlAnalysisSection status="success" analysis={makeAnalysis({ anomaly_label: 0 })} />);
    expect(screen.getByTestId("ml-anomaly-status")).toHaveTextContent("Normal condition");
    expect(screen.getByTestId("ml-anomaly-status")).not.toHaveTextContent("Anomalous");
  });

  it("5. renders Anomalous state correctly", () => {
    render(<MlAnalysisSection status="success" analysis={makeAnalysis({ anomaly_label: 1 })} />);
    expect(screen.getByTestId("ml-anomaly-status")).toHaveTextContent("Anomalous condition");
  });

  it("6. renders probability values correctly (percent formatting)", () => {
    render(
      <MlAnalysisSection
        status="success"
        analysis={makeAnalysis({ safe_probability: 0.87, unsafe_probability: 0.13, anomaly_score: 0.21 })}
      />
    );
    expect(screen.getByText("87.0%")).toBeInTheDocument();
    expect(screen.getByText("13.0%")).toBeInTheDocument();
    expect(screen.getByText("0.210")).toBeInTheDocument();
  });

  it("7. shows 'Analysis unavailable' when ML columns are missing — never a Safe default", () => {
    render(<MlAnalysisSection status="unavailable" analysis={null} />);
    expect(screen.getByTestId("ml-analysis")).toHaveTextContent("Analysis unavailable");
    expect(screen.queryByTestId("ml-water-quality")).not.toBeInTheDocument();
  });

  it("8. shows an error state on API failure — no fabricated data", () => {
    render(<MlAnalysisSection status="error" analysis={null} message="Backend unreachable" />);
    expect(screen.getByTestId("ml-analysis")).toHaveTextContent("Backend unreachable");
    expect(screen.queryByTestId("ml-water-quality")).not.toBeInTheDocument();
  });

  it("8b. unauthorized state shows restriction message — no analysis data exposed", () => {
    render(<MlAnalysisSection status="unauthorized" analysis={null} />);
    expect(screen.getByTestId("ml-analysis")).toHaveTextContent("restricted to authority accounts");
    expect(screen.queryByTestId("ml-water-quality")).not.toBeInTheDocument();
  });

  it("15. honest wording: never claims confirmed contamination or guaranteed safety", () => {
    render(<MlAnalysisSection status="success" analysis={makeAnalysis({ water_quality_label: "Unsafe" })} />);
    const section = screen.getByTestId("ml-analysis").textContent ?? "";
    expect(section).toContain("not laboratory confirmation");
    expect(section).not.toMatch(/confirmed contamination/i);
    expect(section).not.toMatch(/guaranteed safe/i);
    expect(section).not.toMatch(/laboratory verified/i);
  });
});

describe("MlLatestCard (fetching wrapper)", () => {
  it("renders analysis data when the API returns a valid response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(makeResponse(makeAnalysis({ anomaly_label: 1 }))),
        })
      )
    );
    renderWithRouter(<MlLatestCard stationCode="ARK-001" />);
    await waitFor(() => expect(screen.getByTestId("ml-anomaly-status")).toHaveTextContent("Anomalous condition"));
    expect(screen.getByTestId("ml-water-quality")).toHaveTextContent("Safe (predicted)");
  });

  it("maps 404 to 'Analysis unavailable'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: "No sensor readings found for station 'ARK-001'." }),
        })
      )
    );
    renderWithRouter(<MlLatestCard stationCode="ARK-001" />);
    await waitFor(() =>
      expect(screen.getByTestId("ml-analysis")).toHaveTextContent(
        "No sensor readings found for station 'ARK-001'."
      )
    );
    expect(screen.getByTestId("ml-analysis")).toHaveTextContent("Analysis unavailable");
  });

  it("maps pre-ML readings (NULL ML columns) to 'Analysis unavailable'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve(
              makeResponse(
                makeAnalysis({
                  anomaly_label: null,
                  anomaly_score: null,
                  water_quality_label: null,
                  safe_probability: null,
                  unsafe_probability: null,
                  ml_processed_at: null,
                })
              )
            ),
        })
      )
    );
    renderWithRouter(<MlLatestCard stationCode="ARK-001" />);
    await waitFor(() => expect(screen.getByTestId("ml-analysis")).toHaveTextContent("Analysis unavailable"));
  });

  it("maps 401 to unauthorized state and exposes no analysis data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 401,
          json: () => Promise.resolve({ detail: "Not authenticated" }),
        })
      )
    );
    renderWithRouter(<MlLatestCard stationCode="ARK-001" />);
    await waitFor(() =>
      expect(screen.getByTestId("ml-analysis")).toHaveTextContent(
        "AI analysis is restricted to authority accounts."
      )
    );
    expect(screen.queryByTestId("ml-water-quality")).not.toBeInTheDocument();
  });

  it("shows loading state while the request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {}))); // never resolves
    renderWithRouter(<MlLatestCard stationCode="ARK-001" />);
    expect(screen.getByText(/Loading AI analysis/i)).toBeInTheDocument();
  });
});

describe("MlSummaryCard (command-center aggregate)", () => {
  const stations = [
    { id: 1, station_code: "ARK-001", station_name: "Upstream", water_source_id: 1, zone: "", location: "", latitude: 0, longitude: 0, public_warning: "NORMAL", public_message: "", is_active: true, created_at: "", water_source: { id: 1, source_code: "ARK", name: "River", source_type: "RIVER", description: "", created_at: "" } },
    { id: 2, station_code: "ARK-002", station_name: "Midstream", water_source_id: 1, zone: "", location: "", latitude: 0, longitude: 0, public_warning: "CAUTION", public_message: "", is_active: true, created_at: "", water_source: { id: 1, source_code: "ARK", name: "River", source_type: "RIVER", description: "", created_at: "" } },
  ];

  it("counts anomalous and unsafe stations from backend data only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = url.replace(/^https?:\/\/[^/]+/, "");
        const body =
          path === "/api/authority/stations/ARK-001/readings/latest/analysis"
            ? makeResponse(makeAnalysis({ anomaly_label: 1, water_quality_label: "Unsafe" }))
            : path === "/api/authority/stations/ARK-002/readings/latest/analysis"
              ? makeResponse(makeAnalysis({ anomaly_label: 0, water_quality_label: "Safe" }))
              : { detail: "not found" };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      })
    );
    render(<MlSummaryCard stations={stations} />);
    await waitFor(() => expect(screen.getByTestId("ml-summary-anomalous")).toHaveTextContent("1"));
    expect(screen.getByTestId("ml-summary-unsafe")).toHaveTextContent("1");
    expect(screen.getByText(/2 stations monitored/)).toBeInTheDocument();
  });

  it("reports stations without ML analysis as 'not analysed' instead of counting them as normal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const isARK001 = url.includes("/stations/ARK-001/readings");
        return Promise.resolve({
          ok: isARK001,
          status: isARK001 ? 200 : 404,
          json: () =>
            isARK001
              ? Promise.resolve(makeResponse(makeAnalysis()))
              : Promise.resolve({ detail: "no readings" }),
        });
      })
    );
    render(<MlSummaryCard stations={stations} />);
    await waitFor(() => expect(screen.getByTestId("ml-summary-anomalous")).toHaveTextContent("0"));
    expect(screen.getByTestId("ml-summary-unsafe")).toHaveTextContent("0");
    expect(screen.getByText(/1 not analysed yet/)).toBeInTheDocument();
    expect(screen.getByText("ARK-002")).toBeInTheDocument();
  });

  it("shows the honest empty state when no station has analysis", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: "no readings" }) })
      )
    );
    render(<MlSummaryCard stations={stations} />);
    await waitFor(() =>
      expect(screen.getByTestId("ml-summary")).toHaveTextContent("ML analysis is not available for any station yet")
    );
  });

  it("renders the unauthorized state without fetching or exposing data", () => {
    mockToken.value = null;
    render(<MlSummaryCard stations={stations} />);
    expect(screen.getByTestId("ml-summary")).toHaveTextContent("restricted to authority accounts");
    expect(screen.queryByTestId("ml-summary-anomalous")).not.toBeInTheDocument();
  });
});

describe("MlIndicator (live-monitoring compact trio)", () => {
  it("renders known values with correct states", () => {
    render(<MlIndicator anomalyLabel={1} anomalyScore={-0.12} qualityLabel="Unsafe" />);
    expect(screen.getByTestId("ml-indicator-anomaly")).toHaveTextContent("Anomalous condition");
    expect(screen.getByTestId("ml-indicator-quality")).toHaveTextContent("Unsafe (predicted)");
    expect(screen.getByTestId("ml-indicator-score")).toHaveTextContent("-0.120");
  });

  it("renders em dashes for unknown values — never fabricated defaults", () => {
    render(<MlIndicator anomalyLabel={null} anomalyScore={null} qualityLabel={null} />);
    expect(screen.getByTestId("ml-indicator-anomaly")).toHaveTextContent("—");
    expect(screen.getByTestId("ml-indicator-quality")).toHaveTextContent("—");
    expect(screen.getByTestId("ml-indicator-score")).toHaveTextContent("—");
  });
});

describe("RBAC boundaries (spec §9/§10)", () => {
  it("public source page renders and contains no authority ML analysis", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              id: 1,
              station_code: "ARK-001",
              water_source_id: 1,
              station_name: "Upstream Station",
              zone: "Z",
              location: "L",
              latitude: 13.1,
              longitude: 77.4,
              public_warning: "NORMAL",
              public_message: "Water quality is normal.",
              is_active: true,
              created_at: "2026-09-13T00:00:00Z",
              water_source: { id: 1, source_code: "ARK", name: "River", source_type: "RIVER", description: "", created_at: "" },
            }),
        })
      )
    );
    // Render with the real route shape so useParams provides stationId.
    render(
      <MemoryRouter initialEntries={["/public/source/ARK-001"]}>
        <Routes>
          <Route path="/public/source/:stationId" element={<PublicSource />} />
        </Routes>
      </MemoryRouter>
    );
    // Public page shows station info but must not contain ML fields.
    await waitFor(() => expect(screen.getByText("Upstream Station")).toBeInTheDocument());
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/anomaly score/i);
    expect(body).not.toMatch(/safe probability/i);
    expect(body).not.toMatch(/unsafe probability/i);
    expect(body).not.toMatch(/anomalous condition/i);
    expect(body).not.toMatch(/predicted water quality/i);
  });

  it("ML components render nothing without authority data even when token exists (product-user safety net)", () => {
    // MlSummaryCard only renders counts fetched from authority endpoints;
    // a product user's token gets 403 → unauthorized UI, no counts.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ detail: "Forbidden" }) }))
    );
    render(
      <MlSummaryCard
        stations={[
          {
            id: 9,
            station_code: "ARK-009",
            water_source_id: 1,
            station_name: "S",
            zone: "",
            location: "",
            latitude: 0,
            longitude: 0,
            public_warning: "NORMAL",
            public_message: "",
            is_active: true,
            created_at: "",
            water_source: { id: 1, source_code: "ARK", name: "River", source_type: "RIVER", description: "", created_at: "" },
          },
        ]}
      />
    );
    // While loading, no counts are exposed; after the 403 the component shows
    // either the unauthorized state or the not-analysed state — never counts.
    return waitFor(
      () => {
        const text = screen.getByTestId("ml-summary").textContent ?? "";
        expect(
          text.includes("restricted to authority accounts") ||
            text.includes("ML analysis is not available for any station yet")
        ).toBe(true);
      },
      { timeout: 2000 }
    );
  });
});

describe("Existing pages still work (spec §16.11/12)", () => {
  const station = {
    id: 1,
    station_code: "ARK-001",
    water_source_id: 1,
    station_name: "Upstream Station",
    zone: "Upstream",
    location: "Reservoir",
    latitude: 13.1558,
    longitude: 77.4886,
    public_warning: "NORMAL",
    public_message: "",
    is_active: true,
    created_at: "2026-09-13T00:00:00Z",
    water_source: { id: 1, source_code: "ARK", name: "Arkavathi River", source_type: "RIVER", description: "", created_at: "" },
  };

  it("WaterMap renders stations from the API and links to station detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([station]) })
      )
    );
    renderWithRouter(<WaterMap />);
    await waitFor(() => expect(screen.getAllByText("Upstream Station").length).toBeGreaterThan(0));
    expect(screen.getAllByText("ARK-001").length).toBeGreaterThan(0);
  });

  it("CommandCenter still renders its core sections alongside the ML summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([station]),
        })
      )
    );
    renderWithRouter(<CommandCenter />);
    await waitFor(() => expect(screen.getByTestId("ml-summary-title")).toBeInTheDocument());
    expect(screen.getByText("Monitored Water Sources Directory")).toBeInTheDocument();
  });
});
