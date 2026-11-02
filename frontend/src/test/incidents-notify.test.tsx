/**
 * Authority Incidents page — lab notification by email.
 *
 * The page must talk to the real backend (`/authority/incidents`,
 * `/authority/lab-contacts`, `/authority/incidents/{id}/notify-lab`) and must
 * report the delivery outcome exactly as the API returns it: a report that was
 * never handed to SMTP is never shown as emailed.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  IncidentDetail,
  IncidentListItem,
  LabContact,
} from "../lib/api";

const mockToken = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("../lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/auth")>();
  return {
    ...actual,
    getToken: () => mockToken.value,
  };
});

import Incidents from "../pages/authority/Incidents";

/**
 * Match on the request path, not the host: the API base comes from
 * VITE_API_BASE_URL (a LAN address in development), so a hardcoded origin
 * would silently miss every call and turn the tests into 404s.
 */
function endpointOf(url: string): string {
  try {
    return new URL(url, "http://localhost").pathname;
  } catch {
    return url;
  }
}

const contact: LabContact = {
  id: 7,
  name: "Dr Rao",
  organization: "State Water Laboratory",
  email: "lab@example.org",
  phone: null,
  address: null,
  accreditation: null,
  is_active: true,
  created_at: "2026-10-01T10:00:00Z",
};

const listItem: IncidentListItem = {
  id: 1,
  reference: "INC-000001",
  station_code: "ARK-001",
  station_name: "Arkavathi Intake",
  title: "Sudden pH drop with rising turbidity",
  priority: "high",
  status: "raised",
  origin: "manual",
  is_demo: false,
  raised_at: "2026-10-30T09:00:00Z",
  lab_notification_status: "not_notified",
};

function makeDetail(
  overrides: Partial<IncidentDetail> = {}
): IncidentDetail {
  return {
    ...listItem,
    summary: "A rapid drop in pH and rising turbidity were observed.",
    alert_reason: "pH 6.2 below the configured screening range.",
    explanation: null,
    explanation_source: "authority_manual",
    lab_contact: null,
    lab_notified_at: null,
    sample_id: null,
    resolved_at: null,
    resolution_summary: null,
    allowed_transitions: ["lab_notified", "resolved"],
    events: [
      {
        id: 1,
        from_status: null,
        to_status: "raised",
        note: "Incident raised.",
        actor_id: 1,
        created_at: "2026-10-30T09:00:00Z",
      },
    ],
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Builds a fetch mock for the four endpoints the page uses. */
function buildFetch(detailResponse: IncidentDetail) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const path = endpointOf(url);
    if (path.endsWith("/authority/incidents/1/notify-lab")) {
      return jsonResponse(detailResponse);
    }
    if (path.endsWith("/authority/incidents/1")) {
      return jsonResponse(makeDetail());
    }
    if (path.endsWith("/authority/incidents")) {
      const badge =
        detailResponse.lab_notification_status === "not_notified"
          ? listItem
          : { ...listItem, lab_notification_status: detailResponse.lab_notification_status };
      return jsonResponse([badge]);
    }
    if (path.endsWith("/authority/lab-contacts")) {
      return jsonResponse([contact]);
    }
    return jsonResponse({ detail: "Not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

async function openIncident() {
  const user = userEvent.setup();
  await screen.findByText(/Sudden pH drop/);
  await user.click(screen.getByText(/Sudden pH drop/));
  await screen.findByText(/Notify laboratory by email/);
  return user;
}

beforeEach(() => {
  mockToken.value = "test-token";
  sessionStorage.setItem("hydrasense_access_token", "test-token");
});

describe("Incidents — notify lab by email", () => {
  it("emails the report to the selected laboratory and shows the delivered outcome", async () => {
    const sent = makeDetail({
      status: "lab_notified",
      lab_notification_status: "sent",
      lab_notified_at: "2026-10-30T09:30:00Z",
      lab_contact: contact,
      allowed_transitions: ["sample_collected", "resolved"],
    });
    const { fetchMock, calls } = buildFetch(sent);

    render(<Incidents />);
    const user = await openIncident();

    await user.selectOptions(screen.getByLabelText(/Laboratory/), "7");
    await user.type(
      screen.getByLabelText(/Note to the laboratory/),
      "Please confirm the turbidity index."
    );
    await user.click(screen.getByRole("button", { name: /Email report to lab/ }));

    await screen.findByText(/Report emailed to State Water Laboratory/);

    const notifyCall = calls.find((call) =>
      call.url.includes("/notify-lab")
    );
    expect(notifyCall).toBeTruthy();
    expect(notifyCall?.init?.method).toBe("POST");
    expect(notifyCall?.init?.headers).toMatchObject({
      Authorization: "Bearer test-token",
    });
    const body = JSON.parse(String(notifyCall?.init?.body));
    expect(body).toEqual({
      lab_contact_id: 7,
      note: "Please confirm the turbidity index.",
    });
    // The queue badge refreshes from the API afterwards.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(
      await screen.findByText("Report emailed")
    ).toBeInTheDocument();
  });

  it("never claims an email was sent when SMTP is unconfigured", async () => {
    const unconfigured = makeDetail({
      status: "lab_notified",
      lab_notification_status: "smtp_unconfigured",
      lab_notified_at: null,
      lab_contact: contact,
      allowed_transitions: ["sample_collected", "resolved"],
    });
    buildFetch(unconfigured);

    render(<Incidents />);
    const user = await openIncident();

    await user.click(screen.getByRole("button", { name: /Email report to lab/ }));

    await screen.findByText(/NO email was sent to State Water Laboratory/);
    expect(
      screen.getAllByText(/Email not configured/).length
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/Report emailed to/)).not.toBeInTheDocument();
  });

  it("shows a failed delivery as failed, with the retry path still available", async () => {
    const failed = makeDetail({
      status: "lab_notified",
      lab_notification_status: "failed",
      lab_notified_at: null,
      lab_contact: contact,
      allowed_transitions: ["sample_collected", "resolved"],
    });
    buildFetch(failed);

    render(<Incidents />);
    const user = await openIncident();

    await user.click(screen.getByRole("button", { name: /Email report to lab/ }));

    await screen.findByText(/Email delivery to State Water Laboratory <lab@example.org> failed/);
    // The notify action stays usable for a re-send.
    expect(
      screen.getByRole("button", { name: /Email report to lab/ })
    ).toBeEnabled();
  });

  it("keeps laboratory contacts and the report behind authority auth (no token = no fetch)", async () => {
    mockToken.value = null;
    sessionStorage.removeItem("hydrasense_access_token");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<Incidents />);

    await screen.findByText(/session has expired/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
