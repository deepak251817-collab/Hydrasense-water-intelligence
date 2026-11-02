import { useState } from "react";
import { Outlet } from "react-router-dom";
import AuthoritySidebar from "../components/authority/AuthoritySidebar";
import AuthorityTopbar from "../components/authority/AuthorityTopbar";
import SimulationDock from "../components/authority/SimulationDock";

export default function AuthorityLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 font-sans antialiased text-slate-900">
      {/* Dark Navy Operations Sidebar */}
      <AuthoritySidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main Operations Frame */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Operations Topbar */}
        <AuthorityTopbar onMenuClick={() => setSidebarOpen(true)} />

        {/* Dynamic Page Scroll Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-slate-50/50">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Authority-only floating simulation controls (bottom-right). */}
      <SimulationDock />
    </div>
  );
}
