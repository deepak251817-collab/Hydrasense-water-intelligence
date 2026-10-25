import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowRight, Info, Loader2 } from "lucide-react";
import type { ApiError } from "../../lib/api";
import { productApi } from "../../lib/api";
import { clearAuth, getToken } from "../../lib/auth";

export default function Activate() {
  const navigate = useNavigate();
  const [productCode, setProductCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActivate = async (event: React.FormEvent) => {
    event.preventDefault();
    const token = getToken();
    if (!token) {
      navigate("/user/login");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await productApi.activateProduct(productCode, token);
      navigate("/user/dashboard", {
        state: { message: "Device activated successfully." },
      });
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.statusCode === 401) {
        clearAuth();
        navigate("/user/login");
        return;
      }
      setError(apiError.detail || "This product code could not be activated.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-md rounded-3xl border border-slate-200 bg-white px-4 py-12 shadow-sm sm:px-10">
      <Link
        to="/user/dashboard"
        className="mb-6 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Dashboard
      </Link>

      <div className="mb-8 text-center">
        <h2 className="text-2xl font-bold text-slate-900">Activate your Device</h2>
        <p className="mt-2 text-sm text-slate-500">
          Enter the product code found on your HydraSense device packaging or manual.
        </p>
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      <form className="space-y-6" onSubmit={handleActivate}>
        <div>
          <label htmlFor="product-code" className="block text-sm font-medium text-slate-700">
            Product Code
          </label>
          <div className="mt-1">
            <input
              id="product-code"
              type="text"
              required
              value={productCode}
              onChange={(event) => setProductCode(event.target.value)}
              disabled={loading}
              autoComplete="off"
              className="block w-full appearance-none rounded-xl border border-slate-300 px-4 py-3 text-center font-mono uppercase tracking-widest text-slate-900 placeholder-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-cyan-500 disabled:bg-slate-100 sm:text-lg"
              placeholder="HS-KIT-000000"
            />
          </div>
        </div>

        <div className="flex gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
          <Info className="h-5 w-5 shrink-0" aria-hidden="true" />
          <p>
            Codes are checked against registered HydraSense devices. A code that is
            invalid, already claimed by another account, or not activated by the
            manufacturer will be rejected.
          </p>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-600 px-4 py-3 text-sm font-bold text-white hover:bg-cyan-700 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Activating…
            </>
          ) : (
            <>
              <span>Activate &amp; Go to Dashboard</span>
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
