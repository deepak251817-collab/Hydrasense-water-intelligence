/**
 * Demonstration dataset for the three configured rivers ONLY:
 *
 *   Arkavathi River · Cauvery River · Vrishabhavathi River
 *
 * Every location and reading in this file is DEMONSTRATION / SIMULATED data,
 * not verified real-world information. Real telemetry arrives from the
 * FastAPI + MQTT pipeline and replaces these values wherever the app has live
 * data.
 *
 * The project supports exactly four sensors: pH, TDS (mg/L ≈ ppm),
 * temperature (°C) and the analog turbidity RELATIVE INDEX (0–100,
 * higher = cloudier — never NTU). Dissolved oxygen and every other
 * unsupported sensor are deliberately absent.
 */

export interface TrendData {
  time: string;
  pH: number;
  /** Relative turbidity index 0–100 (higher = cloudier) — NOT NTU. */
  turbidity: number;
  tds: number; // mg/L
  healthScore: number;
}

export type RiskLevel = "Stable" | "Watch" | "High" | "Critical";

export interface WaterSource {
  id: string;
  name: string;
  type: "Lake" | "Reservoir" | "Pond" | "River" | "Well";
  location: string;
  latitude: number;
  longitude: number;
  risk: RiskLevel;
  healthScore: number; // 0-100
  pH: number;
  /** Relative turbidity index 0–100 (higher = cloudier) — NOT NTU. */
  turbidity: number;
  tds: number; // mg/L
  temperature: number; // °C
  /** Where these values come from: labelled simulation or physical hardware. */
  dataSource: "simulated" | "esp32";
  trendDirection: "improving" | "stable" | "deteriorating";
  historicalTrend: TrendData[];
  updatedTime: string;
  publicWarning: boolean;
  publicMessage: string;
  publicSuitability: {
    drinking: "Not Recommended" | "Caution" | "Permissible with Treatment";
    domestic: "Safe" | "Caution" | "Restricted";
    irrigation: "Safe" | "Caution" | "Restricted";
    recreation: "Safe" | "Caution" | "Restricted";
    aquaculture: "Safe" | "Caution" | "Restricted";
  };
  aiInsight?: string;
}

export interface Alert {
  id: string;
  sourceId: string;
  sourceName: string;
  type: "turbidity" | "prediction" | "tds" | "ph" | "general";
  title: string;
  description: string;
  severity: "Warning" | "High" | "Critical";
  timestamp: string;
  acknowledged: boolean;
}

export interface SensorProbe {
  id: string;
  parameter: string;
  sensorType: string;
  status: "Healthy" | "Warning" | "Offline";
  currentValue: string;
  battery: number;
  signalStrength: "Excellent" | "Good" | "Fair" | "Poor";
  lastUptime: string;
}

export interface WaterUseCategory {
  id: "drinking" | "domestic" | "irrigation" | "recreation" | "aquaculture";
  title: string;
  icon: string;
  shortDescription: string;
  safetyThresholds: string;
}

export const waterUseOptions: WaterUseCategory[] = [
  {
    id: "drinking",
    title: "Drinking",
    icon: "GlassWater",
    shortDescription: "Direct human consumption and culinary preparation.",
    safetyThresholds:
      "BIS IS 10500: pH 6.5–8.5, TDS ≤ 500 mg/L acceptable (turbidity index is not NTU)",
  },
  {
    id: "domestic",
    title: "Domestic Use",
    icon: "Home",
    shortDescription: "Bathing, dishwashing, laundry, and sanitation.",
    safetyThresholds:
      "BIS IS 10500: pH 6.5–8.5, TDS ≤ 500 mg/L acceptable (ingestion still needs drinking-water screening)",
  },
  {
    id: "irrigation",
    title: "Irrigation",
    icon: "Sprout",
    shortDescription: "Agricultural crops, home gardens, and community landscaping.",
    safetyThresholds: "FAO TDS categories (<450 / 450–2000 / >2000 mg/L), pH 6.5–8.4 reference",
  },
  {
    id: "recreation",
    title: "Swimming / Recreation",
    icon: "Waves",
    shortDescription: "Direct skin contact sports, swimming, and boating.",
    safetyThresholds:
      "pH and turbidity concerns flagged; microbiological testing is required — no suitability claim",
  },
  {
    id: "aquaculture",
    title: "Aquaculture",
    icon: "Fish",
    shortDescription: "Fish farming, aquatic breeding, and biodiversity conservation.",
    safetyThresholds: "Insufficient parameters (no dissolved oxygen / ammonia / salinity sensors)",
  },
];

/**
 * The three demonstration rivers. Each river has its own monitoring
 * location(s); all readings are simulated demonstration values.
 */
export const mockWaterSources: WaterSource[] = [
  {
    id: "RIV-ARK",
    name: "Arkavathi River",
    type: "River",
    location: "Nandi Hills Catchment — demonstration monitoring location",
    latitude: 13.375,
    longitude: 77.674,
    risk: "Watch",
    healthScore: 74,
    pH: 7.1,
    turbidity: 34, // relative index 0–100, not NTU
    tds: 348,
    temperature: 27.4,
    dataSource: "simulated",
    trendDirection: "deteriorating",
    updatedTime: "15 mins ago",
    publicWarning: false,
    publicMessage:
      "Demonstration reading: elevated turbidity index and TDS are being monitored. Simulated data — not a live measurement.",
    aiInsight: "Demonstration trend: the simulated index drifts upward downstream of urban inflows.",
    publicSuitability: {
      drinking: "Not Recommended",
      domestic: "Caution",
      irrigation: "Safe",
      recreation: "Caution",
      aquaculture: "Caution",
    },
    historicalTrend: [
      { time: "06:00", pH: 7.3, turbidity: 26, tds: 310, healthScore: 80 },
      { time: "09:00", pH: 7.2, turbidity: 28, tds: 325, healthScore: 78 },
      { time: "12:00", pH: 7.2, turbidity: 30, tds: 335, healthScore: 76 },
      { time: "15:00", pH: 7.1, turbidity: 32, tds: 342, healthScore: 75 },
      { time: "18:00", pH: 7.1, turbidity: 34, tds: 348, healthScore: 74 },
    ],
  },
  {
    id: "RIV-CAU",
    name: "Cauvery River",
    type: "River",
    location: "Ramnagara Stretch — demonstration monitoring location",
    latitude: 12.717,
    longitude: 77.283,
    risk: "Stable",
    healthScore: 91,
    pH: 7.4,
    turbidity: 15, // relative index 0–100, not NTU
    tds: 274,
    temperature: 27.2,
    dataSource: "simulated",
    trendDirection: "stable",
    updatedTime: "10 mins ago",
    publicWarning: false,
    publicMessage:
      "Demonstration reading: readings sit inside the configured screening ranges. Simulated data — not a live measurement.",
    aiInsight: "Demonstration trend: stable simulated conditions across the sampled window.",
    publicSuitability: {
      drinking: "Caution",
      domestic: "Safe",
      irrigation: "Safe",
      recreation: "Safe",
      aquaculture: "Safe",
    },
    historicalTrend: [
      { time: "06:00", pH: 7.4, turbidity: 14, tds: 268, healthScore: 92 },
      { time: "09:00", pH: 7.4, turbidity: 15, tds: 270, healthScore: 92 },
      { time: "12:00", pH: 7.3, turbidity: 16, tds: 272, healthScore: 91 },
      { time: "15:00", pH: 7.4, turbidity: 15, tds: 273, healthScore: 91 },
      { time: "18:00", pH: 7.4, turbidity: 15, tds: 274, healthScore: 91 },
    ],
  },
  {
    id: "RIV-VRS",
    name: "Vrishabhavathi River",
    type: "River",
    location: "Bengaluru Urban Stretch — demonstration monitoring location",
    latitude: 12.953,
    longitude: 77.541,
    risk: "Critical",
    healthScore: 42,
    pH: 6.7,
    turbidity: 68, // relative index 0–100, not NTU
    tds: 742,
    temperature: 28.4,
    dataSource: "simulated",
    trendDirection: "deteriorating",
    updatedTime: "Just now",
    publicWarning: true,
    publicMessage:
      "Demonstration alert: a significant change in monitored parameters has been detected and the source is under investigation. Simulated data.",
    aiInsight:
      "Demonstration trend: the simulated turbidity index is in the CLOUDIER band (≥55) and TDS is above the acceptable reference.",
    publicSuitability: {
      drinking: "Not Recommended",
      domestic: "Restricted",
      irrigation: "Restricted",
      recreation: "Restricted",
      aquaculture: "Restricted",
    },
    historicalTrend: [
      { time: "06:00", pH: 6.9, turbidity: 52, tds: 640, healthScore: 52 },
      { time: "09:00", pH: 6.9, turbidity: 57, tds: 675, healthScore: 48 },
      { time: "12:00", pH: 6.8, turbidity: 61, tds: 700, healthScore: 46 },
      { time: "15:00", pH: 6.8, turbidity: 65, tds: 724, healthScore: 44 },
      { time: "18:00", pH: 6.7, turbidity: 68, tds: 742, healthScore: 42 },
    ],
  },
];

/** Demonstration alerts — three rivers only, four sensors only, no NTU claims. */
export const mockAlerts: Alert[] = [
  {
    id: "alert-1",
    sourceId: "RIV-VRS",
    sourceName: "Vrishabhavathi River",
    type: "turbidity",
    title: "Critical: Turbidity Index in the CLOUDIER band",
    description:
      "Demonstration alert: the relative turbidity index reached 68/100 (CLOUDIER band ≥ 55, higher = cloudier). This is a sensor index, not an NTU measurement, and it is not compared with any NTU limit.",
    severity: "Critical",
    timestamp: "8 mins ago",
    acknowledged: false,
  },
  {
    id: "alert-2",
    sourceId: "RIV-VRS",
    sourceName: "Vrishabhavathi River",
    type: "tds",
    title: "High: TDS above the acceptable reference",
    description:
      "Demonstration alert: TDS is 742 mg/L, above the BIS IS 10500 acceptable reference of 500 mg/L (permissible 2000 mg/L). Investigation recommended.",
    severity: "High",
    timestamp: "18 mins ago",
    acknowledged: false,
  },
  {
    id: "alert-3",
    sourceId: "RIV-ARK",
    sourceName: "Arkavathi River",
    type: "turbidity",
    title: "Warning: Turbidity Index rising across samples",
    description:
      "Demonstration alert: the relative turbidity index rose from 26 to 34 across consecutive simulated samples. Review recent changes at the source.",
    severity: "Warning",
    timestamp: "45 mins ago",
    acknowledged: false,
  },
];

/** Exactly the four sensors this hardware supports. */
export const mockSensorProbes: SensorProbe[] = [
  {
    id: "probe-ph",
    parameter: "pH Sensor",
    sensorType: "Glass Electrode Potentiometric",
    status: "Healthy",
    currentValue: "7.15 pH",
    battery: 94,
    signalStrength: "Excellent",
    lastUptime: "99.8%",
  },
  {
    id: "probe-turb",
    parameter: "Turbidity Index Sensor",
    sensorType: "Analog Optical (relative index 0–100, not NTU)",
    status: "Warning",
    currentValue: "34 / 100 index",
    battery: 82,
    signalStrength: "Good",
    lastUptime: "99.4%",
  },
  {
    id: "probe-tds",
    parameter: "TDS Sensor",
    sensorType: "Toroidal Conductivity Probe",
    status: "Healthy",
    currentValue: "412 mg/L",
    battery: 89,
    signalStrength: "Excellent",
    lastUptime: "99.9%",
  },
  {
    id: "probe-temp",
    parameter: "Temperature Sensor",
    sensorType: "Digital 1-Wire Probe",
    status: "Healthy",
    currentValue: "28.1 °C",
    battery: 91,
    signalStrength: "Excellent",
    lastUptime: "99.9%",
  },
];

export interface IncidentRecord {
  id: string;
  sourceId: string;
  sourceName: string;
  title: string;
  priority: "Critical" | "High" | "Medium" | "Low";
  status: "Open" | "Investigating" | "Resolved";
  assignedTeam: string;
  reportedAt: string;
  summary: string;
}

export const mockIncidents: IncidentRecord[] = [
  {
    id: "INC-2026-089",
    sourceId: "RIV-VRS",
    sourceName: "Vrishabhavathi River",
    title: "Turbidity Index & TDS Surge",
    priority: "Critical",
    status: "Investigating",
    assignedTeam: "Rapid Response Unit Bengaluru",
    reportedAt: "Today, 06:45 AM",
    summary:
      "Demonstration incident: the relative turbidity index crossed the CLOUDIER band (≥55) while TDS exceeded the 500 mg/L acceptable reference. Simulated demonstration data.",
  },
  {
    id: "INC-2026-084",
    sourceId: "RIV-ARK",
    sourceName: "Arkavathi River",
    title: "Downstream Parameter Drift",
    priority: "High",
    status: "Open",
    assignedTeam: "Catchment Protection Wing",
    reportedAt: "Yesterday, 04:30 PM",
    summary:
      "Demonstration incident: a steady upward drift in the turbidity index and TDS across consecutive simulated samples.",
  },
  {
    id: "INC-2026-077",
    sourceId: "RIV-CAU",
    sourceName: "Cauvery River",
    title: "Stable Baseline Confirmed",
    priority: "Low",
    status: "Resolved",
    assignedTeam: "Riverside Monitoring Team",
    reportedAt: "Aug 18, 2026",
    summary:
      "Demonstration incident: simulated readings stayed within configured screening ranges across the sampled window.",
  },
];

export interface InspectionRecord {
  id: string;
  sourceName: string;
  inspector: string;
  date: string;
  type: "Routine Surveillance" | "Emergency Audit" | "Probe Calibration";
  status: "Completed" | "Scheduled" | "In Review";
  findings: string;
}

export const mockInspections: InspectionRecord[] = [
  {
    id: "INS-4401",
    sourceName: "Cauvery River",
    inspector: "Dr. Arvind Rao",
    date: "Aug 19, 2026",
    type: "Routine Surveillance",
    status: "Completed",
    findings:
      "Demonstration record: four-sensor array reported values inside configured screening ranges. Turbidity reported as a relative index only.",
  },
  {
    id: "INS-4402",
    sourceName: "Vrishabhavathi River",
    inspector: "Field Officer S. Meena",
    date: "Aug 20, 2026",
    type: "Emergency Audit",
    status: "In Review",
    findings:
      "Demonstration record: sample collection complete for laboratory analysis. Turbidity index elevated; NTU comparison requires a calibrated instrument.",
  },
  {
    id: "INS-4403",
    sourceName: "Arkavathi River",
    inspector: "Catchment Team B",
    date: "Aug 22, 2026",
    type: "Probe Calibration",
    status: "Scheduled",
    findings:
      "Demonstration record: scheduled quarterly calibration of the pH and TDS probes with reference solutions.",
  },
];

export interface LabVerificationRecord {
  sampleId: string;
  sourceName: string;
  collectedAt: string;
  testedAt: string;
  certifiedBy: string;
  status: "Certified" | "Pending Lab Analysis" | "Discrepancy Flagged";
  parameters: {
    bod: string;
    cod: string;
    fecalColiform: string;
    heavyMetals: string;
  };
}

export const mockLabRecords: LabVerificationRecord[] = [
  {
    sampleId: "LAB-BLR-2026-902",
    sourceName: "Cauvery River",
    collectedAt: "Aug 16, 2026",
    testedAt: "Aug 18, 2026",
    certifiedBy: "State Water Testing Laboratory (KSPCB)",
    status: "Certified",
    parameters: {
      bod: "3.2 mg/L (Conforms)",
      cod: "14.5 mg/L (Conforms)",
      fecalColiform: "<10 MPN/100ml",
      heavyMetals: "Below detection threshold",
    },
  },
  {
    sampleId: "LAB-BLR-2026-914",
    sourceName: "Vrishabhavathi River",
    collectedAt: "Aug 20, 2026",
    testedAt: "In Progress",
    certifiedBy: "State Environmental Chemistry Lab",
    status: "Pending Lab Analysis",
    parameters: {
      bod: "Awaiting incubation (5-day)",
      cod: "Analysis underway",
      fecalColiform: "Plating in progress",
      heavyMetals: "Spectrometry scheduled",
    },
  },
  {
    sampleId: "LAB-BLR-2026-889",
    sourceName: "Arkavathi River",
    collectedAt: "Aug 12, 2026",
    testedAt: "Aug 15, 2026",
    certifiedBy: "Central Water Quality Monitoring Institute",
    status: "Certified",
    parameters: {
      bod: "6.8 mg/L (Marginal)",
      cod: "28.0 mg/L (Watch)",
      fecalColiform: "45 MPN/100ml",
      heavyMetals: "Lead/Cadmium safe",
    },
  },
];
