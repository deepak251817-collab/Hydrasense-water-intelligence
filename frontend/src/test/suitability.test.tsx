/**
 * Water Suitability Assessment UI tests.
 *
 * These pin down the presentation contract:
 *  - results show the documented standard and the exact per-parameter status;
 *  - non-comparable readings (relative turbidity, uncalibrated, simulated) are
 *    labelled as such and never presented as a measurement;
 *  - missing laboratory tests are listed;
 *  - the intended-use selector switches the displayed assessment;
 *  - the panel is explicitly rule-based, not ML and not a certificate.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  StationSuitabilityResponse,
  WaterSuitabilityAssessment,
} from "../lib/api";

const mockToken = vi.hoisted(() => ({ value: "authority-token" as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return { ...actual, getToken: () => mockToken.value };
});

vi.mock("qrcode", () => ({
  default: { toString: vi.fn(async () => "<svg xmlns='http://www.w3.org/2000/svg'/>") },
}));

import WaterSuitabilitySection from "../components/authority/WaterSuitabilitySection";
import PublicPageQrCard from "../components/authority/PublicPageQrCard";

const NOW = new Date().toISOString();

function drinking(patch: Partial<WaterSuitabilityAssessment> = {}): WaterSuitabilityAssessment {
  return {
    use: "drinking",
    use_label: "Drinking water",
    description: "Potable use against BIS IS 10500.",
    standard_code: "BIS-IS-10500:2012",
    standard: "BIS IS 10500:2012 Drinking Water — Specification (Amd. 4)",
    ruleset_version: "2026.10.1",
    result: "lab_confirmation_required",
    result_label: "Laboratory confirmation required",
    summary:
      "Within acceptable limits: pH, Total dissolved solids. Not available for comparison: Turbidity. Required BIS parameters (microbiological and unmeasured chemical tests) need laboratory confirmation before any drinking-water conclusion.",
    parameters: [
      {
        parameter: "ph",
        label: "pH",
        unit: "",
        value: 7.2,
        status: "within_acceptable",
        status_label: "Within acceptable limit",
        reference: "BIS IS 10500:2012 (Amd. 4), Table 1: pH 6.5–8.5 (acceptable; no relaxation permitted)",
        critical: true,
      },
      {
        parameter: "tds",
        label: "Total dissolved solids",
        unit: "mg/L",
        value: 310,
        status: "within_acceptable",
        status_label: "Within acceptable limit",
        reference: "BIS IS 10500:2012 (Amd. 4), Table 1: TDS 500 mg/L acceptable, 2000 mg/L permissible",
        critical: true,
      },
      {
        parameter: "turbidity",
        label: "Turbidity",
        unit: "NTU",
        value: 68,
        status: "not_comparable",
        status_label: "Not comparable to this criterion",
        reference: "BIS IS 10500:2012 (Amd. 4), Table 1: turbidity 1 NTU acceptable, 5 NTU permissible",
        critical: true,
        note: "Reported as a provisional relative index, not NTU — not comparable to an NTU limit",
      },
    ],
    missing_parameters: [
      {
        parameter: "ecoli",
        label: "E. coli / thermotolerant coliform",
        why: "Absence in 100 mL required (BIS IS 10500 Table 6) — laboratory test",
        required_by: "BIS IS 10500:2012 Drinking Water — Specification (Amd. 4)",
      },
    ],
    measured_values: [
      { parameter: "ph", label: "pH", value: 7.2, unit: "", source: "esp32" },
      { parameter: "tds", label: "Total dissolved solids", value: 310, unit: "mg/L", source: "esp32" },
      { parameter: "turbidity", label: "Turbidity", value: 68, unit: "relative_index_0_100", source: "esp32" },
    ],
    limitations: [
      "BIS IS 10500 requires microbiological (E. coli / thermotolerant coliform) and chemical parameters this station does not measure; passing pH/TDS/turbidity never certifies drinking-water safety.",
    ],
    data_quality: {
      freshness: "fresh",
      age_seconds: 4,
      reading_id: 42,
      reading_timestamp: NOW,
      device_source: "esp32",
      comparable_parameters: ["ph", "tds"],
      excluded_parameters: [
        { parameter: "turbidity", reason: "Reported as a provisional relative index, not NTU" },
      ],
    },
    ...patch,
  };
}

function irrigation(): WaterSuitabilityAssessment {
  return {
    ...drinking(),
    use: "irrigation",
    use_label: "Irrigation",
    description: "Agricultural irrigation against CPCB Class E.",
    standard_code: "CPCB-DBU-E",
    standard: "CPCB Designated Best Use — Class E (irrigation)",
    result: "insufficient_data",
    result_label: "Insufficient data to determine suitability",
    summary: "Within acceptable limits: pH. Not available for comparison: Electrical conductivity, Sodium adsorption ratio, Boron.",
    parameters: [
      {
        parameter: "ph",
        label: "pH",
        unit: "",
        value: 7.2,
        status: "within_acceptable",
        status_label: "Within acceptable limit",
        reference: "CPCB DBU Class E (irrigation / industrial cooling): pH 6.0–8.5",
        critical: true,
      },
      {
        parameter: "ec",
        label: "Electrical conductivity",
        unit: "µS/cm",
        value: null,
        status: "not_measured",
        status_label: "Not measured",
        reference: "CPCB DBU Class E (irrigation / industrial cooling): EC <= 2250 micromhos/cm at 25 °C",
        critical: true,
        note: "Not measured by this station",
      },
    ],
    missing_parameters: [
      {
        parameter: "ec",
        label: "Electrical conductivity",
        why: "Not measured by this station",
        required_by: "CPCB Designated Best Use — Class E (irrigation)",
      },
      {
        parameter: "sar",
        label: "Sodium adsorption ratio",
        why: "Not measured by this station",
        required_by: "CPCB Designated Best Use — Class E (irrigation)",
      },
    ],
    limitations: [
      "TDS is not electrical conductivity: a TDS reading cannot be substituted for the CPCB Class E conductivity limit.",
    ],
    data_quality: {
      freshness: "fresh",
      age_seconds: 4,
      reading_id: 42,
      reading_timestamp: NOW,
      device_source: "esp32",
      comparable_parameters: ["ph"],
      excluded_parameters: [],
    },
  };
}

function response(): StationSuitabilityResponse {
  return {
    station_code: "ARK-001",
    station_name: "Arkavathi Upstream Station",
    generated_at: NOW,
    ruleset_version: "2026.10.1",
    assessments: [drinking(), irrigation()],
  };
}

function mockFetch(body: StationSuitabilityResponse | { detail: string }, status = 200) {
  const fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  mockToken.value = "authority-token";
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("WaterSuitabilitySection", () => {
  it("renders the standard, result, criteria statuses and missing tests", async () => {
    mockFetch(response());
    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    expect(await screen.findByTestId("suitability-result")).toHaveAttribute(
      "data-result",
      "lab_confirmation_required"
    );
    expect(screen.getByText(/BIS IS 10500:2012 Drinking Water/)).toBeInTheDocument();
    expect(screen.getByText("Laboratory confirmation required")).toBeInTheDocument();
    expect(screen.getByTestId("suitability-parameter-ph")).toHaveTextContent("Within acceptable limit");
    expect(screen.getByTestId("suitability-parameter-turbidity")).toHaveTextContent(
      "Not comparable to this criterion"
    );
    expect(screen.getByText(/provisional relative index, not NTU/)).toBeInTheDocument();
    expect(screen.getByTestId("suitability-missing")).toHaveTextContent(
      "E. coli / thermotolerant coliform"
    );
    expect(screen.getByTestId("suitability-freshness")).toHaveTextContent("Fresh data");
  });

  it("switches the assessment when another intended use is selected", async () => {
    mockFetch(response());
    const user = userEvent.setup();
    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    await screen.findByTestId("suitability-result");
    await user.click(screen.getByTestId("suitability-use-irrigation"));

    expect(screen.getByTestId("suitability-result")).toHaveAttribute(
      "data-result",
      "insufficient_data"
    );
    expect(screen.getByText(/CPCB Designated Best Use — Class E \(irrigation\)/)).toBeInTheDocument();
    expect(screen.getByTestId("suitability-missing")).toHaveTextContent("Electrical conductivity");
    expect(screen.getByText(/TDS is not electrical conductivity/)).toBeInTheDocument();
  });

  it("renders backend recommendations with causes, actions and missing assessments", async () => {
    const advised = drinking({
      recommendations: {
        recommendations: [
          {
            parameter: "tds",
            label: "Total dissolved solids",
            direction: "above",
            status: "outside_limits",
            value: 2400,
            unit: "mg/L",
            reason: "Above the configured screening range.",
            urgency: "high",
            possible_causes: ["Possible upstream discharge — not confirmed by this reading."],
            actions: ["Re-sample and repeat the TDS measurement before acting on it."],
            avoid: ["Avoid relying on this water until the reading is re-confirmed."],
          },
        ],
        missing_assessments: [
          "EC, SAR, chloride and boron are not measured by these sensors.",
        ],
        urgency: "high",
        authority_actions: [
          "Collect a labelled grab sample at the station.",
          "Notify the pollution control authority and raise an incident.",
        ],
      },
    });
    mockFetch({ ...response(), assessments: [advised] });

    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    const block = await screen.findByTestId("suitability-recommendations");
    expect(block).toHaveTextContent("high urgency");
    expect(screen.getByTestId("recommendation-tds")).toHaveTextContent(
      "Re-sample and repeat the TDS measurement"
    );
    expect(block).toHaveTextContent("not measured by these sensors");
    expect(screen.getByTestId("authority-actions")).toHaveTextContent(
      "Notify the pollution control authority"
    );
  });

  it("omits the advice block when the backend sends an empty set", async () => {
    const clean = drinking({
      recommendations: {
        recommendations: [],
        missing_assessments: [],
        urgency: null,
        authority_actions: [],
      },
    });
    mockFetch({ ...response(), assessments: [clean] });

    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    await screen.findByTestId("suitability-result");
    expect(screen.queryByTestId("suitability-recommendations")).not.toBeInTheDocument();
  });

  it("never presents the rule-based screening as machine learning", async () => {
    mockFetch(response());
    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    await screen.findByTestId("suitability-result");
    expect(screen.getByText(/not a laboratory certificate and not\s+an ML prediction/)).toBeInTheDocument();
  });

  it("marks stale data and refuses a current conclusion", async () => {
    const stale = drinking({
      result: "insufficient_data",
      result_label: "Insufficient data to determine suitability",
      summary: "The latest reading is older than 60 minutes, so no current suitability conclusion is drawn for this use.",
      data_quality: {
        ...drinking().data_quality,
        freshness: "stale",
        age_seconds: 7200,
      },
    });
    mockFetch({ ...response(), assessments: [stale] });

    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    expect(await screen.findByTestId("suitability-freshness")).toHaveTextContent("Stale data");
    expect(screen.getByTestId("suitability-result")).toHaveTextContent(
      /no current suitability conclusion/
    );
  });

  it("shows the restricted state for authority mode without a token", async () => {
    mockToken.value = null;
    const fetchMock = mockFetch(response());
    render(<WaterSuitabilitySection stationCode="ARK-001" />);

    expect(await screen.findByText(/restricted to authority accounts/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls the authenticated endpoint in authority mode", async () => {
    const fetchMock = mockFetch(response());
    render(<WaterSuitabilitySection stationCode="ARK-001" mode="authority" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = (
      fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>
    )[0];
    expect(String(url)).toContain("/authority/stations/ARK-001/suitability");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer authority-token"
    );
  });

  it("shows a proper error when the assessment cannot be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch")))
    );
    render(<WaterSuitabilitySection stationCode="ARK-001" mode="public" />);

    expect(await screen.findByTestId("suitability-error")).toHaveTextContent(/Network error/);
  });
});

describe("PublicPageQrCard", () => {
  it("encodes the station's public water-body URL", async () => {
    render(<PublicPageQrCard stationCode="ARK-001" />);

    expect(await screen.findByTestId("public-qr-image")).toBeInTheDocument();
    const url = screen.getByTestId("public-qr-url");
    expect(url).toHaveTextContent(/\/public\/source\/ARK-001$/);
    expect(screen.getByText("Open public page").closest("a")).toHaveAttribute(
      "href",
      `${window.location.origin}/public/source/ARK-001`
    );
  });

  it("warns that a localhost QR only works on this machine", async () => {
    render(<PublicPageQrCard stationCode="ARK-001" />);
    expect(await screen.findByText(/points to localhost/)).toBeInTheDocument();
  });

  it("uses VITE_PUBLIC_BASE_URL when configured and drops the localhost warning", async () => {
    vi.stubEnv("VITE_PUBLIC_BASE_URL", "https://hydrasense.example");
    render(<PublicPageQrCard stationCode="ARK-001" />);

    expect(await screen.findByTestId("public-qr-url")).toHaveTextContent(
      "https://hydrasense.example/public/source/ARK-001"
    );
    expect(screen.queryByText(/points to localhost/)).not.toBeInTheDocument();
  });

  it("asks for a station when none is selected", async () => {
    render(<PublicPageQrCard stationCode={null} />);
    expect(await screen.findByText(/Select a station to generate/)).toBeInTheDocument();
  });
});
