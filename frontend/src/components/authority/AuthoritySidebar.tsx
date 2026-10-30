import { NavLink, Link } from "react-router-dom";
import Logo from "../shared/Logo";
import { 
  LayoutDashboard, 
  Droplets, 
  Activity, 
  ShieldAlert, 
  Flame, 
  ClipboardCheck, 
  FlaskConical, 
  Map, 
  LineChart, 
  QrCode,
  X,
  ExternalLink
} from "lucide-react";

interface AuthoritySidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function AuthoritySidebar({ isOpen, onClose }: AuthoritySidebarProps) {
  const navItems = [
    { to: "/authority", label: "Command Center", icon: LayoutDashboard, end: true },
    { to: "/authority/sources", label: "Water Sources", icon: Droplets },
    { to: "/authority/monitoring", label: "Live Monitoring", icon: Activity },
    { to: "/authority/simulation", label: "Simulation", icon: FlaskConical },
    { to: "/authority/alerts", label: "Alerts", icon: ShieldAlert, badge: "3" },
    { to: "/authority/incidents", label: "Incidents", icon: Flame },
    { to: "/authority/inspections", label: "Inspections", icon: ClipboardCheck },
    { to: "/authority/laboratory", label: "Laboratory", icon: FlaskConical },
    { to: "/authority/map", label: "Water Map", icon: Map },
    { to: "/authority/qr", label: "Public QR", icon: QrCode },
    { to: "/authority/analytics", label: "Analytics", icon: LineChart },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-xs lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Authority Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-slate-950 text-slate-200 transition-transform duration-300 lg:static lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Header Branding */}
        <div className="flex h-20 items-center justify-between border-b border-slate-800/80 px-6">
          <Logo variant="dark" to="/authority" size="md" />

          {/* Close button for mobile */}
          <button 
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-900 hover:text-white lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Section Label */}
        <div className="px-6 pt-5 pb-2">
          <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
            Operations & Control
          </span>
        </div>

        {/* Navigation List */}
        <nav className="flex-1 space-y-1 px-3 py-2 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-all duration-150 group relative ${
                    isActive
                      ? "bg-cyan-500/15 text-cyan-300 font-bold"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <div className="flex items-center gap-3">
                      <Icon className={`h-4 w-4 transition-transform duration-200 group-hover:scale-105 ${
                        isActive ? "text-cyan-400" : "text-slate-500 group-hover:text-slate-300"
                      }`} />
                      <span>{item.label}</span>
                    </div>

                    {item.badge && (
                      <span className="rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-extrabold text-white">
                        {item.badge}
                      </span>
                    )}

                    {isActive && (
                      <div className="absolute left-0 top-1/4 h-1/2 w-1 rounded-r bg-cyan-400" />
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Sidebar Footer & Public Switcher */}
        <div className="border-t border-slate-800/80 p-4 space-y-3">
          <Link
            to="/public"
            className="flex items-center justify-between rounded-xl bg-slate-900/90 px-3.5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-900 hover:text-white transition-colors border border-slate-800"
          >
            <span>Citizen Public Portal</span>
            <ExternalLink className="h-3.5 w-3.5 text-cyan-400" />
          </Link>

          <div className="rounded-xl bg-slate-900/60 p-3 border border-slate-800/60">
            <div className="flex items-center gap-2 text-[11px] font-bold text-slate-300">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Screening pipeline ready</span>
            </div>
            <p className="mt-1 text-[10px] text-slate-500 font-medium">
              Threshold profile served by the backend
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
