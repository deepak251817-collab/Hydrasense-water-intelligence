import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  Loader2,
  QrCode as QrCodeIcon,
  RefreshCw,
} from "lucide-react";
import type { ApiError, MonitoringStation, StationQrMetadata } from "../../lib/api";
import { authorityApi } from "../../lib/api";
import { getToken } from "../../lib/auth";

type DownloadFormat = "png" | "svg" | "pdf";

const FORMAT_LABELS: Record<DownloadFormat, string> = {
  png: "PNG image",
  svg: "SVG vector",
  pdf: "PDF label",
};

function fileNameFor(stationCode: string, format: DownloadFormat): string {
  return `${stationCode}-qr.${format}`;
}

export default function QrCodes() {
  const token = getToken();
  const [stations, setStations] = useState<MonitoringStation[]>([]);
  const [selectedCode, setSelectedCode] = useState<string>("");
  const [metadata, setMetadata] = useState<StationQrMetadata | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loadingStations, setLoadingStations] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [downloading, setDownloading] = useState<DownloadFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  // Load the real station list; no mock fallback.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await authorityApi.getAllStations(token);
        if (cancelled) return;
        setStations(rows);
        setSelectedCode((current) => current || rows[0]?.station_code || "");
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError((err as ApiError).detail || "Failed to load monitoring stations.");
      } finally {
        if (!cancelled) setLoadingStations(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Load metadata + preview for the selected station.
  useEffect(() => {
    if (!token || !selectedCode) return;
    let cancelled = false;

    const releasePreview = () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
      setPreviewUrl(null);
    };

    (async () => {
      setLoadingPreview(true);
      setDownloadError(null);
      try {
        const data = await authorityApi.getStationQr(selectedCode, token);
        const blob = await authorityApi.downloadStationQr(selectedCode, "png", token);
        if (cancelled) return;
        setMetadata(data);
        releasePreview();
        const url = URL.createObjectURL(blob);
        previewUrlRef.current = url;
        setPreviewUrl(url);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setMetadata(null);
        releasePreview();
        setError((err as ApiError).detail || "Failed to load the QR code.");
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, selectedCode, refreshKey]);

  useEffect(
    () => () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    },
    []
  );

  const download = async (format: DownloadFormat) => {
    if (!token || !selectedCode) return;
    setDownloading(format);
    setDownloadError(null);
    try {
      const blob = await authorityApi.downloadStationQr(selectedCode, format, token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileNameFor(selectedCode, format);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError((err as ApiError).detail || "Download failed.");
    } finally {
      setDownloading(null);
    }
  };

  if (!token) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto text-amber-500" />
        <p className="mt-3 text-sm font-semibold text-slate-800">Authority sign-in required</p>
        <p className="mt-1 text-xs text-slate-500">
          Sign in with an authority account to generate and download station QR codes.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800 border border-cyan-200">
            <QrCodeIcon className="h-3.5 w-3.5 text-cyan-700" />
            <span>Public Station Codes</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            QR Generator
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Each code deep-links to the public station page with live four-parameter readings and
            rule-based suitability screening. Print the PDF label and place it near the water source.
          </p>
        </div>
      </div>

      {loadingStations ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-cyan-600" />
          <p className="mt-3 text-sm text-slate-500">Loading monitoring stations…</p>
        </div>
      ) : stations.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <QrCodeIcon className="h-8 w-8 mx-auto text-slate-300" />
          <p className="mt-3 text-sm font-semibold text-slate-700">No monitoring stations yet</p>
          <p className="mt-1 text-xs text-slate-500">
            QR codes are generated per station. Add a station before printing public codes.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
            <div>
              <label
                htmlFor="qr-station"
                className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400"
              >
                Monitoring station
              </label>
              <select
                id="qr-station"
                value={selectedCode}
                onChange={(event) => setSelectedCode(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800"
              >
                {stations.map((station) => (
                  <option key={station.station_code} value={station.station_code}>
                    {station.station_code} — {station.station_name}
                  </option>
                ))}
              </select>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-500" />
                <span>{error}</span>
              </div>
            )}

            {loadingPreview ? (
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-8 text-center">
                <Loader2 className="h-5 w-5 animate-spin mx-auto text-cyan-600" />
                <p className="mt-2 text-xs text-slate-500">Generating QR code…</p>
              </div>
            ) : metadata ? (
              <>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
                    Stable public URL
                  </p>
                  <p className="mt-1 break-all font-mono text-xs text-slate-700">
                    {metadata.public_url}
                  </p>
                  <a
                    href={metadata.public_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-cyan-700 hover:text-cyan-800"
                  >
                    Open public page <ExternalLink className="h-3 w-3" />
                  </a>
                </div>

                <div className="flex flex-wrap gap-2">
                  {(Object.keys(FORMAT_LABELS) as DownloadFormat[]).map((format) => (
                    <button
                      key={format}
                      type="button"
                      onClick={() => void download(format)}
                      disabled={downloading !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:border-slate-300 disabled:opacity-50"
                    >
                      {downloading === format ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                      {FORMAT_LABELS[format]}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setRefreshKey((value) => value + 1)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:border-slate-300"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Regenerate
                  </button>
                </div>

                {downloadError && (
                  <p className="text-xs text-red-700">{downloadError}</p>
                )}
              </>
            ) : null}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-3">
            <p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              Preview
            </p>
            <div className="flex items-center justify-center rounded-xl border border-slate-100 bg-slate-50 p-4 min-h-[240px]">
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt={`QR code for station ${selectedCode}`}
                  className="h-56 w-56 rounded-lg bg-white p-2 shadow-sm"
                  data-testid="qr-preview"
                />
              ) : (
                <p className="text-xs text-slate-400">No preview available.</p>
              )}
            </div>
            <p className="text-[11px] leading-relaxed text-slate-500">
              The public page shows only measured values, freshness and rule-based screening. It is a
              preliminary screening, not a laboratory safety certification.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
