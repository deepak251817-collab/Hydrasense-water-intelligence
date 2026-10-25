import { createBrowserRouter, Navigate } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import PublicLayout from "../layouts/PublicLayout";
import AuthorityLayout from "../layouts/AuthorityLayout";

// Public Pages
import Home from "../pages/public/Home";
import WaterCheck from "../pages/public/WaterCheck";
import NearbySources from "../pages/public/NearbySources";
import Warnings from "../pages/public/Warnings";
import MyChecks from "../pages/public/MyChecks";
import PublicSource from "../pages/public/PublicSource";

// User Pages
import UserLayout from "../layouts/UserLayout";
import Login from "../pages/user/Login";
import Register from "../pages/user/Register";
import Activate from "../pages/user/Activate";
import UserDashboard from "../pages/user/UserDashboard";
import UserCheckWater from "../pages/user/UserCheckWater";
import UserDevices from "../pages/user/UserDevices";
import UserHistory from "../pages/user/UserHistory";
import TestResult from "../pages/user/TestResult";

// Authority Pages
import CommandCenter from "../pages/authority/CommandCenter";
import WaterSources from "../pages/authority/WaterSources";
import LiveMonitoring from "../pages/authority/LiveMonitoring";
import Simulation from "../pages/authority/Simulation";
import Alerts from "../pages/authority/Alerts";
import Incidents from "../pages/authority/Incidents";
import Inspections from "../pages/authority/Inspections";
import Laboratory from "../pages/authority/Laboratory";
import WaterMap from "../pages/authority/WaterMap";
import Analytics from "../pages/authority/Analytics";
import StationDetail from "../pages/authority/StationDetail";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Navigate to="/public" replace />,
  },
  {
    path: "/public",
    element: <PublicLayout />,
    children: [
      {
        index: true,
        element: <Home />,
      },
      {
        path: "check-water",
        element: <WaterCheck />,
      },
      {
        path: "sources",
        element: <NearbySources />,
      },
      {
        path: "warnings",
        element: <Warnings />,
      },
      {
        path: "my-checks",
        element: <MyChecks />,
      },
      {
        path: "source/:stationId",
        element: <PublicSource />,
      }
    ],
  },
  {
    path: "/user",
    element: <UserLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/user/dashboard" replace />,
      },
      {
        path: "login",
        element: <Login />,
      },
      {
        path: "register",
        element: <Register />,
      },
      {
        path: "activate",
        element: <Activate />,
      },
      {
        path: "dashboard",
        element: (
          <ProtectedRoute requiredRole="PRODUCT_USER">
            <UserDashboard />
          </ProtectedRoute>
        ),
      },
      {
        path: "check-water",
        element: (
          <ProtectedRoute requiredRole="PRODUCT_USER">
            <UserCheckWater />
          </ProtectedRoute>
        ),
      },
      {
        path: "devices",
        element: (
          <ProtectedRoute requiredRole="PRODUCT_USER">
            <UserDevices />
          </ProtectedRoute>
        ),
      },
      {
        path: "history",
        element: (
          <ProtectedRoute requiredRole="PRODUCT_USER">
            <UserHistory />
          </ProtectedRoute>
        ),
      },
      {
        path: "tests/:testId",
        element: (
          <ProtectedRoute requiredRole="PRODUCT_USER">
            <TestResult />
          </ProtectedRoute>
        ),
      }
    ],
  },
  {
    path: "/authority",
    element: <AuthorityLayout />,
    children: [
      {
        index: true,
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <CommandCenter />
          </ProtectedRoute>
        ),
      },
      {
        path: "sources",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <WaterSources />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <LiveMonitoring />
          </ProtectedRoute>
        ),
      },
      {
        path: "simulation",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Simulation />
          </ProtectedRoute>
        ),
      },
      {
        path: "alerts",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Alerts />
          </ProtectedRoute>
        ),
      },
      {
        path: "incidents",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Incidents />
          </ProtectedRoute>
        ),
      },
      {
        path: "inspections",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Inspections />
          </ProtectedRoute>
        ),
      },
      {
        path: "laboratory",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Laboratory />
          </ProtectedRoute>
        ),
      },
      {
        path: "map",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <WaterMap />
          </ProtectedRoute>
        ),
      },
      {
        path: "analytics",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <Analytics />
          </ProtectedRoute>
        ),
      },
      {
        path: "stations/:stationId",
        element: (
          <ProtectedRoute requiredRole="AUTHORITY">
            <StationDetail />
          </ProtectedRoute>
        ),
      }
    ],
  },
  {
    path: "*",
    element: <Navigate to="/public" replace />,
  },
]);
