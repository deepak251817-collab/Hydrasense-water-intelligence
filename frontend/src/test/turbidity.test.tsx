/**
 * Relative turbidity integration tests (dashboard).
 *
 * The ESP32 publishes a PROVISIONAL RELATIVE INDEX 0-100 (higher = cloudier),
 * which is NOT NTU. These tests pin down:
 *  - the unit is displayed from the stored unit tag (never assumed NTU);
 *  - the firmware status band (CLEARER / MODERATE / CLOUDIER) is shown when valid;
 *  - null measurements render as "Uncalibrated", not as a number;
 *  - unknown-unit readings are labelled as such;
 *  - history plots ONLY relative-index rows — NTU/unknown rows are excluded and
 *    counted in the caption, so two units never share one axis;
 *  - API failure / empty history states are handled.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { LatestReading, StationReading } from "../lib/api";

const mockToken = vi.hoisted(() => ({ value: "authority-token" as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return { ...actual, getToken: () => mockToken.value };
});

import TelemetryStatusCard from "../components/authority/TelemetryStatusCard";

const NOW = new Date().toISOString();

function makeLatest(overrides: Partial<LatestReading> = {}): LatestReading {
  return {
    station_code: "ARK-001",
    device_id: "ESP32-HS-001",
    timestamp: NOW,
    pH: null,
    turbidity: 68.2,
    turbidity_unit: "relative_index_0_100",
    turbidity_status: "CLOUDIER",
    tds: null,
    temperature: 27.1,
    source: "esp32",
    diagnostics: {
      turbidity: {
        unit: "relative_index_0_100",
        raw_adc: 8431,
        voltage_v: 1.054,
        sensor_output_v: 1.581,
        relative_index: 68.2,
        relative_status: "CLOUDIER",
        calibration_status: "provisional_index",
      },
      temperature: { sensor: "DS18B20", valid: true },
      device: { uptime_ms: 69112, wifi_rssi_dbm: -41, seq: 7, errors: [] },
    },
    ...overrides,
  };
}

function makeRow(overrides: Partial<StationReading> = {}): StationReading {
  return {
    id: 1,
    station_id: 1,
    station_code: "ARK-001",
    device_id: "ESP32-HS-001",
    timestamp: NOW,
    pH: null,
    turbidity: 55.0,
    turbidity_unit: "relative_index_0_100",
    turbidity_status: "CLOUDIER",
    tds: null,
    temperature: 27.0,
    source: "esp32",
    diagnostics: null,
    created_at: NOW,
    ...overrides,
  };
}

function mockApi(latest: LatestReading, history: StationReading[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/readings/latest")
        ? latest
        : url.includes("/readings")
          ? history
          : null;
      return Promise.resolve({
        ok: body !== null,
        status: body !== null ? 200 : 404,
        json: async () => body ?? { detail: "not found" },
      });
    })
  );
}

beforeEach(() => {
  mockToken.value = "authority-token";
  vi.unstubAllGlobals();
});

describe("TelemetryStatusCard — relative turbidity", () => {
  it("shows the relative index, its firmware status band and an explicit unit", async () => {
    mockApi(makeLatest(), [makeRow()]);
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(await screen.findByText("Relative Turbidity Index")).toBeInTheDocument();
    expect(screen.getByText("68.2")).toBeInTheDocument();
    expect(screen.getByText("/ 100")).toBeInTheDocument();
    expect(screen.getByTestId("turbidity-status")).toHaveTextContent("CLOUDIER");
    expect(
      screen.getByText(/Provisional relative index — not NTU/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Higher = cloudier · not NTU/)).toBeInTheDocument();
  });

  it("labels NTU simulator readings as NTU (no relative-index claim)", async () => {
    mockApi(
      makeLatest({
        turbidity: 4.8,
        turbidity_unit: "ntu",
        turbidity_status: null,
        source: "simulator",
        diagnostics: null,
      }),
      []
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(await screen.findByText("Turbidity")).toBeInTheDocument();
    expect(screen.getByText("4.8")).toBeInTheDocument();
    expect(screen.getByText("NTU")).toBeInTheDocument();
    expect(screen.queryByText("Relative Turbidity Index")).not.toBeInTheDocument();
  });

  it("flags an unknown turbidity unit instead of assuming NTU", async () => {
    mockApi(
      makeLatest({
        turbidity: 12.0,
        turbidity_unit: null,
        turbidity_status: null,
        source: "esp32",
        diagnostics: null,
      }),
      []
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(await screen.findByText("Turbidity")).toBeInTheDocument();
    expect(screen.getByText("(unit unknown)")).toBeInTheDocument();
    expect(screen.getByText(/Unit not recorded for this reading/)).toBeInTheDocument();
    expect(screen.queryByText("NTU")).not.toBeInTheDocument();
  });

  it("renders a null turbidity as Uncalibrated, never as 0", async () => {
    mockApi(
      makeLatest({
        turbidity: null,
        turbidity_unit: null,
        turbidity_status: null,
        diagnostics: { turbidity: { calibration_status: "pending", valid: false, error: "ads1115 unavailable" } },
      }),
      []
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    // pH, turbidity and TDS tiles all render the honest "Uncalibrated" state.
    expect((await screen.findAllByText("Uncalibrated")).length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("0 / 100")).not.toBeInTheDocument();
  });

  it("plots only relative-index history and excludes NTU/unknown-unit rows", async () => {
    const history = [
      makeRow({ id: 1, timestamp: NOW, turbidity: 68.2, turbidity_status: "CLOUDIER" }),
      makeRow({ id: 2, timestamp: NOW, turbidity: 30.4, turbidity_status: "MODERATE" }),
      // Simulator NTU value — must NOT be plotted on the index axis.
      makeRow({
        id: 3,
        timestamp: NOW,
        turbidity: 4.8,
        turbidity_unit: "ntu",
        turbidity_status: null,
        source: "simulator",
      }),
      // Legacy row with unknown unit — also excluded.
      makeRow({ id: 4, timestamp: NOW, turbidity: 12.0, turbidity_unit: null, turbidity_status: null }),
    ];
    mockApi(makeLatest(), history);
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(await screen.findByText(/Showing 2 relative-index readings/)).toBeInTheDocument();
    expect(
      screen.getByText(/2 NTU\/unknown-unit reading\(s\) excluded/)
    ).toBeInTheDocument();
    // The excluded NTU/unknown numeric values must not appear in the index table.
    expect(screen.queryByText("4.8 / 100")).not.toBeInTheDocument();
    expect(screen.queryByText("12.0 / 100")).not.toBeInTheDocument();
    expect(screen.getByText("68.2 / 100")).toBeInTheDocument();
    expect(screen.getByText("30.4 / 100")).toBeInTheDocument();
  });

  it("handles empty history without inventing a chart", async () => {
    mockApi(makeLatest({ turbidity: null, turbidity_unit: null, turbidity_status: null }), []);
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(
      await screen.findByText(/No relative-index readings yet/)
    ).toBeInTheDocument();
    expect(screen.queryByTestId("turbidity-history-chart")).not.toBeInTheDocument();
  });

  it("keeps the latest reading visible when history fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/readings/latest")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => makeLatest(),
          });
        }
        return Promise.resolve({ ok: false, status: 500, json: async () => ({ detail: "boom" }) });
      })
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    await waitFor(() => expect(screen.getByText("68.2")).toBeInTheDocument());
    expect(
      await screen.findByText(/Reading history is unavailable right now/)
    ).toBeInTheDocument();
  });

  it("shows a loading state until the first response arrives", async () => {
    const pending: Array<() => void> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        new Promise((resolve) => {
          const url = String(input);
          pending.push(() =>
            resolve({
              ok: true,
              status: 200,
              json: async () =>
                url.includes("/readings/latest") ? makeLatest() : [makeRow()],
            })
          );
        })
      )
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(screen.getByText("Loading the latest telemetry…")).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent("Loading");

    await waitFor(() => expect(pending.length).toBeGreaterThan(0));
    pending.forEach((release) => release());
    await waitFor(() =>
      expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent("Online")
    );
  });

  it("explains when the station has no readings yet (404)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({ detail: "No sensor readings found" }),
        })
      )
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(
      await screen.findByText("No readings received for this station yet.")
    ).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent("No data");
  });

  it("handles unauthorized access without leaking readings", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 403,
          json: async () => ({ detail: "Forbidden" }),
        })
      )
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(
      await screen.findByText(/not authorized to view hardware telemetry/)
    ).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent(
      "Unauthorized"
    );
    expect(screen.queryByTestId("telemetry-source")).not.toBeInTheDocument();
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch")))
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    expect(await screen.findByText(/Network error/)).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent("Error");
  });

  it("requests the selected station's readings (not another station's)", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/readings/latest") ? makeLatest() : [makeRow()];
      return Promise.resolve({ ok: true, status: 200, json: async () => body });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TelemetryStatusCard stationCode="ARK-002" />);

    await waitFor(() => expect(screen.getByText("68.2")).toBeInTheDocument());
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(
      urls.some((url) => url.includes("/authority/stations/ARK-002/readings/latest"))
    ).toBe(true);
    expect(urls.some((url) => url.includes("ARK-001"))).toBe(false);
  });

  it("distinguishes simulated readings from physical hardware", async () => {
    mockApi(makeLatest(), [makeRow()]);
    const { unmount } = render(<TelemetryStatusCard stationCode="ARK-001" />);
    expect(await screen.findByTestId("telemetry-source")).toHaveTextContent(
      "Physical hardware (ESP32)"
    );
    unmount();

    mockApi(
      makeLatest({ source: "simulator", turbidity_unit: "ntu", turbidity_status: null }),
      []
    );
    render(<TelemetryStatusCard stationCode="ARK-001" />);
    expect(await screen.findByTestId("telemetry-source")).toHaveTextContent("Simulated");
  });

  it("renders a stale reading with the Stale link badge", async () => {
    const stale = new Date(Date.now() - 60_000).toISOString();
    mockApi(makeLatest({ timestamp: stale }), [makeRow({ timestamp: stale })]);
    render(<TelemetryStatusCard stationCode="ARK-001" />);

    await waitFor(() =>
      expect(screen.getByTestId("telemetry-link-status")).toHaveTextContent("Stale")
    );
    expect(screen.getByText("68.2")).toBeInTheDocument();
  });
});
