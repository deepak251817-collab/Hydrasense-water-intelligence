import { useState } from "react";
import { 
  waterUseOptions, 
  mockWaterSources 
} from "../../data/mockData";
import type { WaterUseCategory } from "../../data/mockData";
import WaterUseCard from "../../components/public/WaterUseCard";
import { 
  CheckCircle2, 
  AlertTriangle, 
  ShieldAlert, 
  Sparkles, 
  RotateCcw, 
  Info, 
  FileCheck2,
  MapPin,
  ArrowRight
} from "lucide-react";
import { Link } from "react-router-dom";

export default function WaterCheck() {
  const [selectedUse, setSelectedUse] = useState<WaterUseCategory["id"]>("drinking");
  const [selectedSourceId, setSelectedSourceId] = useState<string>("source-tg-halli");
  const [isChecking, setIsChecking] = useState<boolean>(false);
  const [hasResult, setHasResult] = useState<boolean>(false);

  const selectedUseOption = waterUseOptions.find((u) => u.id === selectedUse) || waterUseOptions[0];
  const selectedSource = mockWaterSources.find((s) => s.id === selectedSourceId) || mockWaterSources[0];

  const handleStartCheck = () => {
    setIsChecking(true);
    setTimeout(() => {
      setIsChecking(false);
      setHasResult(true);
    }, 600);
  };

  const getScreeningResult = () => {
    // Generate realistic contextual screening result
    if (selectedUse === "drinking") {
      if (selectedSource.risk === "Stable") {
        return {
          status: "CAUTION — TREATMENT REQUIRED",
          badgeColor: "bg-amber-100 text-amber-800 border-amber-300",
          icon: AlertTriangle,
          headline: "Preliminary Screening: Treatment Advised",
          why: [
            "Raw river water requires secondary disinfection and filtration before potable use.",
            `The relative turbidity index is ${selectedSource.turbidity} / 100 (higher = cloudier, not NTU); NTU compliance needs a calibrated instrument.`,
            "Microbiological parameters (e.g., coliform bacteria) cannot be measured by these sensors alone.",
          ],
          recommendation: "Boiling, certified multi-stage RO/UV filtration, or authorized municipal pipeline treatment is required before drinking.",
        };
      }
      return {
        status: "NOT RECOMMENDED FOR DRINKING",
        badgeColor: "bg-red-100 text-red-800 border-red-300",
        icon: ShieldAlert,
        headline: "High Risk for Direct Consumption",          why: [
            `The relative turbidity index is ${selectedSource.turbidity} / 100 (CLOUDIER demo band ≥ 55), indicating high suspended solids.`,
            `Recent water-quality telemetry is ${selectedSource.trendDirection} at this location.`,
            `Current Health Index rating is ${selectedSource.healthScore}/100 with elevated total dissolved solids (${selectedSource.tds} mg/L).`,
          ],
        recommendation: "Avoid direct consumption. Do not use for drinking or culinary preparation without certified laboratory verification and high-grade purification.",
      };
    }

    if (selectedUse === "domestic") {
      if (selectedSource.risk === "Critical") {
        return {
          status: "RESTRICTED DOMESTIC USE",
          badgeColor: "bg-red-100 text-red-800 border-red-300",
          icon: ShieldAlert,
          headline: "Severe Water Condition",
          why: [
            "A high turbidity index and elevated TDS indicate heavy suspended and dissolved loads.",
            "Water may cause skin irritation or stain washing fixtures.",
          ],
          recommendation: "Do not use for bathing, washing utensils, or laundry until public advisories are lifted.",
        };
      }
      return {
        status: "CAUTION — SUITABLE WITH CARE",
        badgeColor: "bg-amber-100 text-amber-800 border-amber-300",
        icon: AlertTriangle,
        headline: "Acceptable for Non-Potable Domestic Tasks",
        why: [
          "pH level and conductivity are within general domestic washing guidelines.",
          "Settling or pre-filtration is recommended to remove particulate matter.",
        ],
        recommendation: "Suitable for cleaning and outdoor maintenance. Basic filtration recommended for laundry.",
      };
    }

    if (selectedUse === "irrigation") {
      if (selectedSource.risk === "Critical") {
        return {
          status: "RESTRICTED FOR EDIBLE CROPS",
          badgeColor: "bg-orange-100 text-orange-800 border-orange-300",
          icon: AlertTriangle,
          headline: "High Salinity & Turbidity Risk",
          why: [
            `TDS level (${selectedSource.tds} mg/L) may cause salt buildup in soil.`,
            "Runoff contamination could harm sensitive plant root systems.",
          ],
          recommendation: "Restrict to non-edible landscaping. Flush soil periodically with clean water.",
        };
      }
      return {
        status: "ACCEPTABLE FOR IRRIGATION",
        badgeColor: "bg-emerald-100 text-emerald-800 border-emerald-300",
        icon: CheckCircle2,
        headline: "Normal Agricultural Suitability",
        why: [
          "TDS and pH are within standard agricultural tolerance ranges.",
          "Dissolved nutrients and minerals support general vegetation growth.",
        ],
        recommendation: "Good for general crops, community garden watering, and lawn irrigation.",
      };
    }

    if (selectedUse === "recreation") {
      if (selectedSource.risk === "Critical" || selectedSource.risk === "High") {
        return {
          status: "SWIMMING & CONTACT NOT ADVISED",
          badgeColor: "bg-red-100 text-red-800 border-red-300",
          icon: ShieldAlert,
          headline: "Recreational Contact Warning Active",
          why: [
            "The turbidity index is in the CLOUDIER demo band; microbiological risk cannot be assessed with these sensors.",
            "Algal blooms or bacterial proliferation require laboratory testing to rule out.",
          ],
          recommendation: "Avoid full body immersion swimming or skin contact. Secondary contact boating permitted with caution.",
        };
      }
      return {
        status: "CAUTION FOR RECREATION",
        badgeColor: "bg-amber-100 text-amber-800 border-amber-300",
        icon: AlertTriangle,
        headline: "Moderate Contact Permissible",
        why: [
          "Water clarity is moderate.",
          "Check local municipal signs before swimming.",
        ],
        recommendation: "Rinse with fresh clean tap water after recreational skin exposure.",
      };
    }

    // Aquaculture default — no dissolved-oxygen / ammonia / salinity sensors,
    // so no suitability verdict can be produced from four readings.
    return {
      status: "INSUFFICIENT PARAMETERS",
      badgeColor: "bg-slate-100 text-slate-700 border-slate-300",
      icon: ShieldAlert,
      headline: "Insufficient parameters for aquaculture",
      why: [
        "Dissolved oxygen, ammonia, nitrite and salinity are not measured by this hardware, and no species-specific criteria are configured.",
        `Available readings: pH ${selectedSource.pH}, TDS ${selectedSource.tds} mg/L, temperature ${selectedSource.temperature} °C, turbidity index ${selectedSource.turbidity} / 100 (not NTU).`,
      ],
      recommendation: "Measure dissolved oxygen and the species-specific water-chemistry parameters before stocking or maintaining aquatic culture.",
    };
  };

  const result = getScreeningResult();
  const ResultIcon = result.icon;

  return (
    <div className="mx-auto max-w-5xl py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Page Header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-cyan-100 px-3 py-1 text-xs font-bold text-cyan-800">
          <FileCheck2 className="h-3.5 w-3.5 text-cyan-700" />
          <span>Intended-Use Water Screening</span>
        </div>
        <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
          Check Water Suitability
        </h1>
        <p className="mt-1 text-sm text-slate-500 max-w-2xl leading-relaxed">
          Select your intended use and reference water source to get an instantaneous, easy-to-understand screening of current water conditions.
        </p>
      </div>

      {/* Mandatory Regulatory Disclaimer Alert */}
      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4.5 text-xs text-amber-950 flex items-start gap-3">
        <Info className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-bold text-amber-900">Important Screening Notice</p>
          <p className="leading-relaxed text-amber-800">
            This is a screening result based on parameters currently measured by HydraSense IoT sensor nodes. 
            <strong> It does not replace laboratory testing or statutory water-safety certification.</strong>
          </p>
        </div>
      </div>

      {/* Step 1: Choose Water Source */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-cyan-700">Step 1</span>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight mt-0.5">
              Select Monitored Water Body
            </h2>
          </div>
          <span className="text-xs font-medium text-slate-400">5 Monitored Locations</span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {mockWaterSources.map((source) => (
            <button
              key={source.id}
              type="button"
              onClick={() => {
                setSelectedSourceId(source.id);
                setHasResult(false);
              }}
              className={`flex items-start justify-between rounded-xl p-3.5 border text-left transition-all ${
                selectedSourceId === source.id
                  ? "border-cyan-600 bg-cyan-50/40 ring-2 ring-cyan-600/20"
                  : "border-slate-200 hover:border-slate-300 bg-white"
              }`}
            >
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {source.type}
                </span>
                <h4 className="text-sm font-bold text-slate-900 mt-0.5">
                  {source.name}
                </h4>
                <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                  <MapPin className="h-3 w-3" />
                  <span>{source.location}</span>
                </div>
              </div>

              <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                source.risk === "Critical" ? "bg-red-100 text-red-700" :
                source.risk === "High" ? "bg-orange-100 text-orange-700" :
                source.risk === "Watch" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"
              }`}>
                {source.risk}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Step 2: Choose Intended Use */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-cyan-700">Step 2</span>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight mt-0.5">
              What will you use this water for?
            </h2>
          </div>
          <span className="text-xs font-semibold text-slate-400">Choose one primary use</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {waterUseOptions.map((useOption) => (
            <WaterUseCard
              key={useOption.id}
              useOption={useOption}
              isSelected={selectedUse === useOption.id}
              onSelect={(id) => {
                setSelectedUse(id);
                setHasResult(false);
              }}
            />
          ))}
        </div>

        {/* Start Check Trigger CTA */}
        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-100">
          <div className="text-xs text-slate-500">
            Selected: <strong className="text-slate-800">{selectedUseOption.title}</strong> at <strong className="text-slate-800">{selectedSource.name}</strong>
          </div>

          <button
            type="button"
            onClick={handleStartCheck}
            disabled={isChecking}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-600 px-8 py-3.5 text-sm font-bold text-white shadow-md hover:bg-cyan-500 transition-all cursor-pointer disabled:opacity-50"
          >
            {isChecking ? (
              <>
                <Sparkles className="h-4 w-4 animate-spin" />
                <span>Screening Water Parameters...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4.5 w-4.5" />
                <span>Start Water Check</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Step 3: Screening Result Modal/Card */}
      {hasResult && (
        <div className="rounded-3xl border-2 border-cyan-500 bg-white p-6 sm:p-8 shadow-xl space-y-6 animate-in fade-in duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
            <div>
              <span className="text-[10px] font-extrabold uppercase tracking-widest text-cyan-700">
                HydraSense Screening Result
              </span>
              <h2 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight mt-0.5">
                {result.headline}
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Evaluation for <strong>{selectedUseOption.title}</strong> at <strong>{selectedSource.name}</strong>
              </p>
            </div>

            <span className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-extrabold uppercase tracking-wider ${result.badgeColor}`}>
              <ResultIcon className="h-4 w-4" />
              <span>{result.status}</span>
            </span>
          </div>

          {/* Why Explanation Section */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Why this screening result?
            </h3>
            <ul className="space-y-2">
              {result.why.map((reason, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-slate-700 leading-relaxed">
                  <div className="h-1.5 w-1.5 rounded-full bg-cyan-600 shrink-0 mt-1.5" />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Recommendation Box */}
          <div className="rounded-2xl border border-cyan-100 bg-cyan-50/50 p-5">
            <div className="flex items-center gap-2 text-cyan-900 font-bold text-xs uppercase tracking-wider">
              <Sparkles className="h-4 w-4 text-cyan-700" />
              <span>Recommended Action</span>
            </div>
            <p className="mt-2 text-sm text-slate-800 font-medium leading-relaxed">
              {result.recommendation}
            </p>
          </div>

          {/* Critical Disclaimer Notice */}
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-[11px] text-slate-500 leading-relaxed">
            <strong>HydraSense Certification Notice:</strong> This screening represents real-time sensor parameters (pH, Turbidity, TDS, Temperature, DO) calibrated against public guidelines. Chemical residues, microbial counts, or heavy metals must be verified through certified laboratory testing before high-consequence usage.
          </div>

          {/* Footer Actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <button
              type="button"
              onClick={() => setHasResult(false)}
              className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 hover:text-slate-900"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Check another use or water source</span>
            </button>

            <Link
              to="/public/sources"
              className="inline-flex items-center gap-1.5 text-xs font-bold text-cyan-700 hover:text-cyan-800"
            >
              <span>Explore nearby monitored lakes</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
