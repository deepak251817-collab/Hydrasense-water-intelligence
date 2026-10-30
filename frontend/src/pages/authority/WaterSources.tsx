import { useState } from "react";
import { mockWaterSources } from "../../data/mockData";
import WaterSourceCard from "../../components/authority/WaterSourceCard";
import PrototypeBanner from "../../components/authority/PrototypeBanner";
import { Droplets, Search, Filter, Plus, FileSpreadsheet } from "lucide-react";

export default function WaterSources() {
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("All");

  const filteredSources = mockWaterSources.filter((s) => {
    const matchesSearch =
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.location.toLowerCase().includes(search.toLowerCase());
    const matchesRisk = riskFilter === "All" || s.risk === riskFilter;
    return matchesSearch && matchesRisk;
  });

  return (
    <div className="space-y-6">
      <PrototypeBanner
        feature="Water source directory cards and filters"
        missing="The backend exposes GET /api/authority/stations with real station identity, location and public warning; this directory should be rebuilt on it, and the map/detail pages should use station_code rather than demo identifiers."
      />

      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
            <Droplets className="h-3.5 w-3.5 text-cyan-700" />
            <span>Water Quality Network Registry</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            Monitored Water Sources
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Full inventory of regional aquatic telemetry nodes, baseline ratings, and risk classifications.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-xs"
          >
            <FileSpreadsheet className="h-4 w-4 text-slate-500" />
            <span>Export CSV</span>
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-bold text-white hover:bg-slate-800 shadow-xs"
          >
            <Plus className="h-4 w-4 text-cyan-400" />
            <span>Register New Node</span>
          </button>
        </div>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search nodes by name or location..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-4 py-2 text-xs font-medium text-slate-800 outline-none focus:border-cyan-500 focus:bg-white"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <Filter className="h-3.5 w-3.5 text-slate-400 mr-1 shrink-0" />
          {["All", "Stable", "Watch", "High", "Critical"].map((risk) => (
            <button
              key={risk}
              type="button"
              onClick={() => setRiskFilter(risk)}
              className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-all whitespace-nowrap ${
                riskFilter === risk
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {risk}
            </button>
          ))}
        </div>
      </div>

      {/* Grid of Water Source Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filteredSources.map((source) => (
          <WaterSourceCard key={source.id} source={source} />
        ))}
      </div>
    </div>
  );
}
