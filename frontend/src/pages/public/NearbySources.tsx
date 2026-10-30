import { useState } from "react";
import { mockWaterSources } from "../../data/mockData";
import PublicSourceCard from "../../components/public/PublicSourceCard";
import DemoDataNotice from "../../components/public/DemoDataNotice";
import { Search, Filter, Droplet, Info } from "lucide-react";

export default function NearbySources() {
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("All");

  const filteredSources = mockWaterSources.filter((source) => {
    const matchesSearch =
      source.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      source.location.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === "All" || source.type === typeFilter;
    return matchesSearch && matchesType;
  });

  return (
    <div className="mx-auto max-w-7xl py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      <DemoDataNotice>
        Real stations and their public suitability results are available on the
        station pages (scan a station QR code) and through the water check flow.
      </DemoDataNotice>

      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-cyan-100 px-3 py-1 text-xs font-bold text-cyan-800">
          <Droplet className="h-3.5 w-3.5 text-cyan-700" />
          <span>Public Water Network</span>
        </div>
        <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
          Monitored Water Sources
        </h1>
        <p className="mt-1 text-sm text-slate-500 max-w-2xl">
          View public water condition screening indicators for lakes, reservoirs, and community water bodies across the Bengaluru metropolitan region.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by lake name or location..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-4 py-2.5 text-sm text-slate-800 outline-none focus:border-cyan-500 focus:bg-white transition-all"
          />
        </div>

        {/* Type Filter Buttons */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <Filter className="h-4 w-4 text-slate-400 shrink-0 mr-1" />
          {["All", "Lake", "Reservoir", "Pond"].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setTypeFilter(type)}
              className={`rounded-xl px-3.5 py-2 text-xs font-bold transition-all whitespace-nowrap ${
                typeFilter === type
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {/* Source Cards Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
          <span>Showing {filteredSources.length} monitored sources</span>
          <span>Updated via continuous IoT telemetry</span>
        </div>

        {filteredSources.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center">
            <Info className="mx-auto h-8 w-8 text-slate-400" />
            <h3 className="mt-3 text-base font-bold text-slate-800">No sources found</h3>
            <p className="mt-1 text-xs text-slate-400">
              Try adjusting your search criteria or type filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {filteredSources.map((source) => (
              <PublicSourceCard key={source.id} source={source} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
