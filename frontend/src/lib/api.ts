// API Client for HydraSense Backend

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

export interface ApiError {
  detail?: string;
  message?: string;
  statusCode?: number;
  /** Machine-readable code from structured API errors (e.g. device_offline). */
  code?: string;
  /** Validation details for structured API errors (e.g. invalid readings). */
  errors?: string[];
}

interface FetchOptions extends RequestInit {
  headers?: Record<string, string>;
}

/**
 * Generic fetch wrapper for API calls
 */
async function fetchApi<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const data = await response.json();

    if (!response.ok) {
      const rawDetail = data?.detail;
      const structured = rawDetail && typeof rawDetail === "object" ? rawDetail : null;
      const error: ApiError = {
        detail:
          typeof rawDetail === "string"
            ? rawDetail
            : structured?.message || data?.message || "Unknown error",
        statusCode: response.status,
        code: structured?.code || data?.code,
        errors: structured?.errors,
      };
      throw error;
    }

    return data as T;
  } catch (error) {
    if (error instanceof TypeError) {
      throw { detail: "Network error - unable to reach server" };
    }
    throw error;
  }
}

/**
 * GET request without authentication
 */
export async function apiGet<T>(endpoint: string): Promise<T> {
  return fetchApi<T>(endpoint, { method: "GET" });
}

/**
 * POST request without authentication
 */
export async function apiPost<T>(
  endpoint: string,
  body?: unknown
): Promise<T> {
  return fetchApi<T>(endpoint, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

/**
 * GET request with JWT authentication
 */
export async function apiGetAuth<T>(
  endpoint: string,
  token: string
): Promise<T> {
  return fetchApi<T>(endpoint, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
}

/**
 * POST request with JWT authentication
 */
export async function apiPostAuth<T>(
  endpoint: string,
  body: unknown,
  token: string
): Promise<T> {
  return fetchApi<T>(endpoint, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ============= API Response Types =============

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: "PRODUCT_USER" | "AUTHORITY";
  is_active: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: "PRODUCT_USER" | "AUTHORITY";
  user: User;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  role?: "PRODUCT_USER" | "AUTHORITY";
  product_code?: string;
}

export interface ProductDevice {
  id: number;
  product_code: string;
  device_id: string;
  device_type: string;
  status: string;
  owner_id?: number;
  activated_at?: string;
  created_at: string;
}

// ============= Product-user water testing =============

export type WaterSourceCode =
  | "tap"
  | "borewell"
  | "well"
  | "tank"
  | "surface"
  | "other";

export type IntendedUseCode =
  | "drinking"
  | "domestic"
  | "irrigation"
  | "general"
  | "swimming"
  | "aquaculture";

export type ReadingMode = "live" | "demo";

export type ParameterStatus =
  | "within_range"
  | "below_project_target"
  | "above_acceptable"
  | "above_permissible"
  | "below_reference"
  | "above_reference"
  | "no_restriction"
  | "slight_restriction"
  | "severe_restriction"
  | "not_comparable"
  | "not_measured"
  | "invalid"
  | "informational";

export type OverallStatus =
  | "WITHIN_PROJECT_TARGETS"
  | "REVIEW_RECOMMENDED"
  | "NOT_RECOMMENDED_BY_SCREENING"
  | "INCONCLUSIVE";

export interface ProductReasonDetail {
  parameter: string;
  label: string;
  value: number | null;
  unit: string;
  status: ParameterStatus;
  status_label: string;
  reference: string;
  reason: string;
  calibration_limitation: string | null;
  next_step: string;
}

export interface ProductStabilityAssessment {
  status:
    | "waiting_for_data"
    | "collecting"
    | "stabilizing"
    | "stable"
    | "unstable"
    | "offline"
    | "sensor_error";
  status_label: string;
  message: string;
  stable: boolean;
  stale: boolean;
  connection: "connected" | "connecting" | "offline" | "error" | "no_data";
  valid_samples: number;
  required_samples: number;
  span_seconds: number;
  required_span_seconds: number;
  progress: number;
  age_seconds: number | null;
  latest_timestamp: string | null;
  latest_reading_id: number | null;
  stale_after_seconds: number;
  offline_after_seconds: number;
  firmware_publish_interval_seconds: number;
  sensor_errors: string[];
  calibration: Record<string, string>;
  per_parameter: Record<
    string,
    {
      label: string;
      min: number;
      max: number;
      median: number;
      range: number;
      tolerance: number;
      stable: boolean;
    }
  >;
}

export interface ProductReadingAssessment {
  parameter: string;
  label: string;
  value: number | null;
  unit: string;
  status: ParameterStatus;
  status_label: string;
  reference: string;
  note?: string | null;
}

export interface ProductOverallAssessment {
  status: OverallStatus;
  label: string;
  summary: string;
  reasons: string[];
  reason_details?: ProductReasonDetail[];
}

export interface ProductAttentionItem {
  parameter: string;
  label: string;
  value: number | null;
  unit: string;
  status: ParameterStatus;
  status_label: string;
  message: string;
}

export interface ProductSuitabilityCriterion {
  parameter: string;
  label: string;
  value: number | null;
  unit: string;
  status: ParameterStatus;
  status_label: string;
  reference: string;
  note?: string | null;
}

export interface ProductSuitability {
  use: IntendedUseCode;
  use_label: string;
  description: string;
  standard_code: string;
  standard: string;
  criteria_version: string;
  result: OverallStatus;
  result_label: string;
  summary: string;
  criteria_available: boolean;
  criteria: ProductSuitabilityCriterion[];
  limitations: string[];
  reference_profile?: Record<string, unknown>;
}

export interface ProductDataQuality {
  demo_mode: boolean;
  reading_mode: ReadingMode;
  freshness: "fresh" | "stale" | "simulated";
  age_seconds: number | null;
  calibration_status: "calibrated" | "provisional" | "simulated" | "unknown";
  calibration_verified: boolean;
  stability: ProductStabilityAssessment | null;
  errors: string[];
  warnings: string[];
}

export interface ProductPrediction {
  available: boolean;
  message: string;
  model_version: string | null;
  horizon_minutes: number | null;
}

export interface ProductTestAssessment {
  criteria_version: string;
  intended_use: IntendedUseCode;
  intended_use_label: string;
  reading_mode: ReadingMode;
  reading_timestamp: string | null;
  readings: {
    ph: ProductReadingAssessment;
    tds: ProductReadingAssessment;
    turbidity: ProductReadingAssessment;
    temperature: ProductReadingAssessment;
  };
  overall: ProductOverallAssessment;
  attention: ProductAttentionItem[];
  suitability: ProductSuitability;
  data_quality: ProductDataQuality;
  next_steps: string[];
  prediction: ProductPrediction;
  reference_profile?: Record<string, unknown>;
}

export interface ProductWaterTest {
  id: number;
  test_code: string;
  water_source: WaterSourceCode;
  water_source_label: string;
  intended_use: IntendedUseCode;
  intended_use_label: string;
  reading_mode: ReadingMode;
  reading_source: string;
  device_id: string;
  device_name: string;
  ph: number | null;
  tds: number | null;
  turbidity: number | null;
  turbidity_unit: string | null;
  turbidity_index?: number | null;
  temperature: number | null;
  reading_timestamp: string | null;
  created_at: string;
  overall_status: OverallStatus;
  overall_label: string;
  criteria_version: string;
  assessment: ProductTestAssessment;
}

export interface ProductWaterTestSummary {
  id: number;
  test_code: string;
  water_source: WaterSourceCode;
  water_source_label: string;
  intended_use: IntendedUseCode;
  intended_use_label: string;
  reading_mode: ReadingMode;
  overall_status: OverallStatus;
  overall_label: string;
  ph: number | null;
  tds: number | null;
  turbidity: number | null;
  turbidity_unit: string | null;
  turbidity_index?: number | null;
  temperature: number | null;
  reading_timestamp: string | null;
  created_at: string;
}

export interface ProductWaterTestList {
  total: number;
  items: ProductWaterTestSummary[];
}

export interface ProductDeviceReading {
  ph: number | null;
  turbidity: number | null;
  turbidity_unit: string | null;
  turbidity_index?: number | null;
  turbidity_status: string | null;
  tds: number | null;
  temperature: number | null;
  timestamp: string;
  source: string;
  calibration: Record<string, string>;
}

export interface ProductDeviceStatus {
  device_id: string;
  device_name: string;
  product_code: string;
  status: string;
  connected: boolean;
  last_seen: string | null;
  reading_age_seconds: number | null;
  reading: ProductDeviceReading | null;
  note: string;
}

export interface ProductOverview {
  total_tests: number;
  latest_test: ProductWaterTestSummary | null;
  recent_tests: ProductWaterTestSummary[];
  device: ProductDeviceStatus | null;
}

/** One danger-level alert derived from a real reading or a saved test. */
export interface ProductAlertItem {
  parameter: string;
  label: string;
  value: number | null;
  unit: string;
  severity: "critical" | "warning";
  title: string;
  message: string;
  reference: string;
  next_step: string;
  timestamp: string;
  source: string;
  simulated: boolean;
  test_id?: number | null;
  intended_use?: string;
}

export interface ProductAlertList {
  total: number;
  items: ProductAlertItem[];
  critical_count: number;
  warning_count: number;
}

export type SimulationScenario =
  | "normal"
  | "gradual_deterioration"
  | "sudden_change"
  | "sensor_fault";

export interface SimulationSample {
  id: number;
  station_code: string;
  source_code: string | null;
  timestamp: string;
  scenario: string;
  step: number;
  ph: number | null;
  tds: number | null;
  temperature: number | null;
  turbidity_index: number | null;
  turbidity_status: string | null;
  fault_sensor: string | null;
  source: "simulator";
  simulated: true;
}

export interface SimulationState {
  running: boolean;
  station_code: string | null;
  source_code: string | null;
  scenario: SimulationScenario | string;
  seed: number | null;
  interval_seconds: number;
  step: number;
  samples_generated: number;
  started_at: string | null;
  last_sample_at: string | null;
  simulated: true;
  label: string;
  scenarios: string[];
  recent_samples: SimulationSample[];
}

export interface LiveLatestReading {
  reading_id: number | null;
  timestamp: string | null;
  ph: number | null;
  tds: number | null;
  turbidity: number | null;
  turbidity_unit: string | null;
  turbidity_index?: number | null;
  turbidity_status: string | null;
  temperature: number | null;
  source: string | null;
}

export interface LiveAssessmentResponse {
  station_code: string;
  station_name: string;
  water_source_name: string;
  device_id: string | null;
  device_name: string;
  connection: "connected" | "connecting" | "offline" | "error" | "no_data";
  connection_label: string;
  last_received: string | null;
  live: boolean;
  poll_interval_seconds: number;
  stability: ProductStabilityAssessment;
  latest: LiveLatestReading | null;
  assessment: ProductTestAssessment;
  test_id: string | null;
  assessment_id: number | null;
  assessment_persisted: boolean;
  criteria_version: string;
}

export interface WaterSourceResponse {
  id: number;
  source_code: string;
  name: string;
  source_type: string;
  description?: string;
  created_at: string;
}

/**
 * ML analysis for a single sensor reading (Phase 6 backend schema: MLAnalysisResponse).
 *
 * All fields are nullable: readings ingested before ML integration (or when the
 * ML service was unavailable) legitimately have NULL ML columns.
 *
 * Honesty (matches backend wording):
 * - `anomaly_label` = 1 marks an *anomalous condition* (unusual sensor pattern)
 *   identified by the Isolation Forest; 0 = normal pattern.
 * - `water_quality_label` is the Random Forest *predicted water-quality class*
 *   ("Safe" / "Unsafe") on the benchmark dataset.
 * Neither is laboratory confirmation, guaranteed safety, guaranteed
 * contamination, or causal pollution detection.
 */
export interface MLAnalysis {
  anomaly_label: number | null; // 1 = anomalous condition, 0 = normal pattern
  anomaly_score: number | null; // Isolation Forest decision function (higher = more typical)
  water_quality_label: string | null; // predicted water-quality class: "Safe" | "Unsafe"
  safe_probability: number | null; // in [0, 1]
  unsafe_probability: number | null; // in [0, 1]
  ml_processed_at: string | null; // ISO datetime; null = not processed
}

/**
 * Per-sensor raw diagnostics reported by physical station hardware
 * (backend `diagnostics` JSON on a sensor reading). Raw ADC counts and
 * measured voltages — NOT calibrated engineering values.
 */
export interface SensorDiagnostics {
  raw_adc?: number;
  voltage_v?: number;
  calibration_status?: string; // "pending" | "provisional_index" | "calibrated" (device-reported)
  valid?: boolean;
  error?: string | null;
  sensor?: string;
  /** Turbidity only: unit tag from the ESP32. "relative_index_0_100" means
   * the numeric `turbidity` field is a PROVISIONAL relative index
   * (0-100, higher = cloudier), NOT NTU. */
  unit?: string;
  /** Turbidity only: reconstructed sensor output voltage (A2 × divider). */
  sensor_output_v?: number;
  /** Turbidity only: the 0-100 relative index (mirrors the top-level field). */
  relative_index?: number | null;
  /** Turbidity only: "CLEARER" | "MODERATE" | "CLOUDIER" (null when invalid). */
  relative_status?: string | null;
}

/** The `device` entry firmware adds to diagnostics (health/sequence). */
export interface DeviceHealthDiagnostics {
  uptime_ms?: number;
  wifi_rssi_dbm?: number;
  seq?: number;
  errors?: string[];
  [key: string]: number | string[] | undefined;
}

export interface DeviceDiagnostics {
  uptime_ms?: number;
  wifi_rssi_dbm?: number;
  seq?: number;
  errors?: string[];
  [sensor: string]:
    | SensorDiagnostics
    | DeviceHealthDiagnostics
    | number
    | string[]
    | undefined;
}

/**
 * Authority payload: sensor reading information + ML analysis
 * (Phase 6 backend schema: ReadingAnalysisResponse).
 *
 * Sensor values are nullable: NULL means the device has NO honest
 * measurement for it (uncalibrated sensor or sensor fault) — rendered as
 * "Uncalibrated", never as a fabricated number or a default "Safe".
 * `source` distinguishes "esp32" (physical hardware) from "simulator".
 */
export interface ReadingAnalysisResponse {
  reading_id: number;
  station_id: number;
  station_code: string;
  device_id: string;
  timestamp: string;
  created_at: string;
  ph: number | null;
  turbidity: number | null;
  /** "relative_index_0_100" (ESP32 index — NOT NTU) | "ntu" | null (unknown). */
  turbidity_unit?: string | null;
  turbidity_index?: number | null;
  /** CLEARER / MODERATE / CLOUDIER for relative-index rows. */
  turbidity_status?: string | null;
  tds: number | null;
  temperature: number | null;
  source: string;
  diagnostics: DeviceDiagnostics | null;
  ml: MLAnalysis;
}

/**
 * Latest raw reading for a station (GET …/readings/latest) — same nullable
 * sensor semantics as ReadingAnalysisResponse, without ML results.
 */
export interface LatestReading {
  station_code: string;
  device_id: string;
  timestamp: string;
  pH: number | null;
  turbidity: number | null;
  /** "relative_index_0_100" = ESP32 provisional index (NOT NTU),
   * "ntu" = simulated NTU-style value, null = unit unknown. */
  turbidity_unit?: string | null;
  turbidity_index?: number | null;
  /** Firmware band for relative-index rows: CLEARER / MODERATE / CLOUDIER. */
  turbidity_status?: string | null;
  tds: number | null;
  temperature: number | null;
  source: string;
  diagnostics: DeviceDiagnostics | null;
}

/**
 * One row of station reading history (GET …/readings). Same nullable values
 * and turbidity unit semantics as LatestReading.
 */
export interface StationReading {
  id: number;
  station_id: number;
  station_code: string | null;
  device_id: string;
  timestamp: string;
  pH: number | null;
  turbidity: number | null;
  turbidity_unit?: string | null;
  turbidity_index?: number | null;
  turbidity_status?: string | null;
  tds: number | null;
  temperature: number | null;
  source: string;
  diagnostics: DeviceDiagnostics | null;
  created_at: string;
}

/**
 * One model entry from GET /authority/ml/status — public metadata only
 * (file NAME, role, feature contract, load state), never filesystem paths.
 */
export interface MLModelStatus {
  key: string;
  name: string;
  role: string;
  file: string;
  features: string[];
  live_inference: boolean;
  artifact_present: boolean;
  loaded: boolean;
}

/** Classification metrics computed by ml/scripts/build_evaluation_report.py. */
export interface MLEvaluationMetrics {
  n_samples?: number;
  accuracy?: number;
  balanced_accuracy?: number;
  precision_macro?: number;
  recall_macro?: number;
  f1_macro?: number;
  f1_weighted?: number;
  roc_auc_unsafe?: number;
  confusion_matrix?: {
    labels: string[];
    matrix: number[][];
    row_semantics: string;
  };
  [key: string]: unknown;
}

/**
 * Machine-readable evaluation report (ml/reports/evaluation_report.json).
 * Every metric is computed from saved repository artifacts at report time —
 * none are hardcoded. Absent sections are simply missing; they are never
 * filled with placeholder numbers.
 */
export interface MLEvaluationReport {
  schema_version: string;
  generated_at: string;
  generator: string;
  environment?: Record<string, string>;
  honesty_policy: string;
  random_forest?: {
    available: boolean;
    task: string;
    live_inference: boolean;
    dataset?: { n_test_samples?: number; [key: string]: unknown };
    metrics?: MLEvaluationMetrics;
    [key: string]: unknown;
  };
  isolation_forest?: {
    available: boolean;
    task: string;
    live_inference: boolean;
    dataset?: { n_scored_readings?: number; note?: string; [key: string]: unknown };
    summary?: {
      anomalies_flagged?: number;
      anomaly_rate?: number;
      score_min?: number;
      score_max?: number;
      score_mean?: number;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  limitations?: string[];
  [key: string]: unknown;
}

// ============= Water Suitability Assessment =============

export type SuitabilityParameterStatus =
  | "within_acceptable"
  | "within_permissible"
  | "outside_limits"
  | "not_measured"
  | "not_comparable";

export type SuitabilityResultCode =
  | "preliminary_suitable"
  | "treatment_required"
  | "outside_limits"
  | "lab_confirmation_required"
  | "insufficient_data";

export interface SuitabilityParameter {
  parameter: string;
  label: string;
  unit: string;
  value: number | null;
  status: SuitabilityParameterStatus;
  status_label: string;
  reference: string;
  critical: boolean;
  note?: string | null;
}

export interface SuitabilityMissingParameter {
  parameter: string;
  label: string;
  why: string;
  required_by: string;
}

export interface SuitabilityMeasuredValue {
  parameter: string;
  label: string;
  value: number;
  unit: string;
  source: string;
}

export interface SuitabilityDataQuality {
  freshness: "fresh" | "delayed" | "stale" | "no_data";
  age_seconds: number | null;
  reading_id: number | null;
  reading_timestamp: string | null;
  device_source: string | null;
  comparable_parameters: string[];
  excluded_parameters: { parameter: string; reason?: string | null }[];
}

export interface WaterSuitabilityAssessment {
  use: string;
  use_label: string;
  description: string;
  standard_code: string;
  standard: string;
  ruleset_version: string;
  result: SuitabilityResultCode;
  result_label: string;
  summary: string;
  parameters: SuitabilityParameter[];
  missing_parameters: SuitabilityMissingParameter[];
  measured_values: SuitabilityMeasuredValue[];
  limitations: string[];
  data_quality: SuitabilityDataQuality;
}

/** GET /{authority|public}/stations/{code}/suitability */
export interface StationSuitabilityResponse {
  station_code: string;
  station_name: string;
  generated_at: string;
  ruleset_version: string;
  assessments: WaterSuitabilityAssessment[];
}

/** Public-safe latest reading for the QR water-body page. */
export interface PublicLatestReading {
  station_code: string;
  timestamp: string;
  pH: number | null;
  turbidity: number | null;
  turbidity_unit: string | null;
  turbidity_index?: number | null;
  turbidity_status: string | null;
  tds: number | null;
  temperature: number | null;
  source: string;
}

export interface PublicReadingHistoryRow extends PublicLatestReading {
  id: number;
}

/** GET /authority/ml/status — model health + evaluation report (authority-only). */
export interface MLStatusResponse {
  models: MLModelStatus[];
  evaluation_available: boolean;
  evaluation: MLEvaluationReport | null;
  report: string | null;
  generated_at: string | null;
}

export interface MonitoringStation {
  id: number;
  station_code: string;
  water_source_id: number;
  station_name: string;
  zone: string;
  location: string;
  latitude: number;
  longitude: number;
  public_warning: string;
  public_message: string;
  is_active: boolean;
  created_at: string;
  water_source: WaterSourceResponse;
}

// Public API (no auth required)
export const publicApi = {
  getStationByCode: (stationCode: string) =>
    apiGet<MonitoringStation>(`/public/stations/${stationCode}`),

  /** Latest public-safe reading for a station (QR water-body page). */
  getLatestReading: (stationCode: string) =>
    apiGet<PublicLatestReading>(`/public/stations/${stationCode}/readings/latest`),

  /** Recent public-safe readings, newest first. */
  getReadingHistory: (stationCode: string, limit = 50) =>
    apiGet<PublicReadingHistoryRow[]>(
      `/public/stations/${stationCode}/readings?limit=${limit}`
    ),

  /** Standards-based suitability assessment (public, no login required). */
  getSuitability: (stationCode: string) =>
    apiGet<StationSuitabilityResponse>(
      `/public/stations/${stationCode}/suitability`
    ),
};

// Auth API (no auth required)
export const authApi = {
  login: (email: string, password: string) =>
    apiPost<LoginResponse>("/auth/login", { email, password }),

  register: (data: RegisterRequest) =>
    apiPost<User>("/auth/register", data),
};

// Product User API (requires PRODUCT_USER JWT)
export const productApi = {
  getProfile: (token: string) =>
    apiGetAuth<User>("/product/me", token),

  getDevices: (token: string) =>
    apiGetAuth<ProductDevice[]>("/product/devices", token),

  getOverview: (token: string) =>
    apiGetAuth<ProductOverview>("/product/overview", token),

  getDeviceStatus: (token: string) =>
    apiGetAuth<ProductDeviceStatus>("/product/device-status", token),

  activateProduct: (productCode: string, token: string) =>
    apiPostAuth<{
      id: number;
      product_code: string;
      device_id: string;
      device_name: string;
      status: string;
    }>("/product/activate", { product_code: productCode }, token),

  startTest: (
    data: {
      water_source: WaterSourceCode;
      intended_use: IntendedUseCode;
      reading_mode: ReadingMode;
      aquaculture_context?: string;
    },
    token: string
  ) => apiPostAuth<ProductWaterTest>("/product/tests", data, token),

  getTests: (
    token: string,
    options: { limit?: number; dateFrom?: string; dateTo?: string } = {}
  ) => {
    const params = new URLSearchParams();
    if (options.limit) params.set("limit", String(options.limit));
    if (options.dateFrom) params.set("date_from", options.dateFrom);
    if (options.dateTo) params.set("date_to", options.dateTo);
    const query = params.toString();
    return apiGetAuth<ProductWaterTestList>(
      `/product/tests${query ? `?${query}` : ""}`,
      token
    );
  },

  getTest: (testId: number, token: string) =>
    apiGetAuth<ProductWaterTest>(`/product/tests/${testId}`, token),

  /**
   * Danger-level alerts for this account's water: derived from the latest
   * live reading of the user's own device plus their recent saved tests.
   * Nothing is invented — each entry carries the measured value, the
   * configured reference and whether the source was live or simulated.
   */
  getAlerts: (token: string, limit = 20) =>
    apiGetAuth<ProductAlertList>(`/product/alerts?limit=${limit}`, token),
};

// Simulation API (requires AUTHORITY JWT) — clearly labelled SIMULATED data
export const simulationApi = {
  getState: (token: string) =>
    apiGetAuth<SimulationState>("/simulation/state", token),

  start: (
    data: {
      station_code: string;
      scenario: SimulationScenario;
      seed?: number | null;
      interval_seconds?: number;
    },
    token: string
  ) => apiPostAuth<SimulationState>("/simulation/start", data, token),

  pause: (token: string) =>
    apiPostAuth<SimulationState>("/simulation/pause", {}, token),

  generate: (
    data: {
      station_code?: string;
      scenario: SimulationScenario;
      seed?: number | null;
      count?: number;
    },
    token: string
  ) => apiPostAuth<SimulationState>("/simulation/generate", data, token),
};

// ---------------------------------------------------------------------------
// Baseline forecasting (authority-only, honest availability)
// ---------------------------------------------------------------------------

export interface ForecastPoint {
  timestamp: string;
  value: number;
  lower: number;
  upper: number;
}

export interface ForecastModelInfo {
  name: string;
  evaluation: string;
  train_size: number;
  test_size: number;
  mae: number;
  rmse: number;
  baseline_mae: number;
  baseline_rmse: number;
}

export interface ForecastParameter {
  parameter: string;
  label: string;
  unit: string;
  status: "ready" | "unavailable";
  reason: string | null;
  message: string | null;
  last_observed: number | null;
  last_observed_at: string | null;
  model: ForecastModelInfo | null;
  uncertainty: { method: string; width: number; note: string } | null;
  points: ForecastPoint[];
}

export interface ForecastResponse {
  station_code: string;
  generated_at: string;
  horizon_hours: number;
  status: "ready" | "unavailable";
  unavailable_reason: string | null;
  message: string;
  data_sources: Record<string, number>;
  trained_on_simulated: boolean;
  readiness: {
    min_samples_required: number;
    min_span_days_required: number;
    observed_span_days: number;
    parameters: {
      parameter: string;
      valid_samples: number;
      span_days: number;
      sufficient: boolean;
    }[];
  };
  parameters: ForecastParameter[];
}

// Authority API (requires AUTHORITY JWT)
export const authorityApi = {
  getProfile: (token: string) =>
    apiGetAuth<User>("/authority/me", token),

  getAllStations: (token: string) =>
    apiGetAuth<MonitoringStation[]>("/authority/stations", token),

  /** ML analysis for a specific sensor reading (authority-only). */
  getReadingAnalysis: (readingId: number, token: string) =>
    apiGetAuth<ReadingAnalysisResponse>(
      `/authority/readings/${readingId}/analysis`,
      token
    ),

  /** Latest sensor reading for a station plus its ML analysis (authority-only). */
  getLatestStationAnalysis: (stationCode: string, token: string) =>
    apiGetAuth<ReadingAnalysisResponse>(
      `/authority/stations/${stationCode}/readings/latest/analysis`,
      token
    ),

  /** Latest sensor reading for a station — raw values + diagnostics, no ML (authority-only). */
  getLatestReading: (stationCode: string, token: string) =>
    apiGetAuth<LatestReading>(
      `/authority/stations/${stationCode}/readings/latest`,
      token
    ),

  /** Recent readings for a station, newest first (authority-only). */
  getStationReadings: (stationCode: string, token: string, limit = 50) =>
    apiGetAuth<StationReading[]>(
      `/authority/stations/${stationCode}/readings?limit=${limit}`,
      token
    ),

  /** Model health + evaluation report (authority-only, read-only). */
  getMlStatus: (token: string) =>
    apiGetAuth<MLStatusResponse>("/authority/ml/status", token),

  /** Standards-based suitability screening for the latest station reading. */
  getStationSuitability: (stationCode: string, token: string) =>
    apiGetAuth<StationSuitabilityResponse>(
      `/authority/stations/${stationCode}/suitability`,
      token
    ),

  /** Stable-reading live assessment for the selected intended use. */
  getLiveAssessment: (
    stationCode: string,
    token: string,
    use: IntendedUseCode = "drinking",
    aquacultureContext?: string
  ) => {
    const params = new URLSearchParams({ use });
    if (aquacultureContext) params.set("aquaculture_context", aquacultureContext);
    return apiGetAuth<LiveAssessmentResponse>(
      `/authority/stations/${stationCode}/live-assessment?${params.toString()}`,
      token
    );
  },

  /**
   * Honest baseline forecast (authority-only). Returns forecast points only for
   * parameters whose model beat a persistence baseline on a chronological
   * holdout; otherwise `status = "unavailable"` with an explicit reason.
   */
  getForecast: (stationCode: string, token: string, horizonHours = 24) =>
    apiGetAuth<ForecastResponse>(
      `/authority/stations/${stationCode}/forecast?horizon_hours=${horizonHours}`,
      token
    ),
};

/**
 * True when the reading's ML analysis actually ran (all result fields present).
 * Readings processed before Phase 6 — or while the ML service was unavailable —
 * have NULL ML columns and must render as "Analysis unavailable", never as
 * fabricated "Normal"/"Safe" defaults.
 */
export function hasMLAnalysis(ml: MLAnalysis | null | undefined): boolean {
  if (!ml) return false;
  return (
    ml.anomaly_label !== null &&
    ml.anomaly_score !== null &&
    ml.water_quality_label !== null &&
    ml.safe_probability !== null &&
    ml.unsafe_probability !== null
  );
}
