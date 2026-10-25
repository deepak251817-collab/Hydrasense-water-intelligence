import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Download, ExternalLink, Loader2, QrCode, TriangleAlert } from "lucide-react";

/**
 * QR code for a station's public water-body page.
 *
 * The encoded URL is the real public route `/public/source/<station_code>`,
 * resolved by the backend against the database. The base origin comes from
 * `VITE_PUBLIC_BASE_URL` when configured (needed so phones on the LAN can open
 * the page), otherwise the current browser origin is used and the card says so
 * explicitly — a localhost URL only works on this machine.
 */
export default function PublicPageQrCard({
  stationCode,
}: {
  stationCode: string | null;
}) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const configuredBase = (import.meta.env.VITE_PUBLIC_BASE_URL as string | undefined)?.replace(
    /\/$/,
    ""
  );
  const base =
    configuredBase ||
    (typeof window !== "undefined" ? window.location.origin : "");
  const publicUrl = stationCode ? `${base}/public/source/${stationCode}` : null;
  const isLocalhost = /localhost|127\.0\.0\.1/i.test(base);

  useEffect(() => {
    if (!publicUrl) return;
    let cancelled = false;
    QRCode.toString(publicUrl, { type: "svg", margin: 1, width: 220 })
      .then((markup) => {
        if (!cancelled) {
          setSvg(`data:image/svg+xml;utf8,${encodeURIComponent(markup)}`);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [publicUrl]);

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs"
      data-testid="public-qr-card"
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <QrCode className="h-4.5 w-4.5 text-cyan-600" />
          <h3 className="text-sm font-bold text-slate-900">Public Water-Body QR</h3>
        </div>
        <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2.5 py-0.5">
          Scan to open
        </span>
      </div>

      {!stationCode ? (
        <p className="mt-4 text-sm text-slate-500">
          Select a station to generate its public QR code.
        </p>
      ) : failed ? (
        <p className="mt-4 flex items-start gap-2 text-sm text-red-800 bg-red-50 border border-red-200 rounded-xl p-3">
          <TriangleAlert className="h-5 w-5 shrink-0 text-red-500" />
          Could not generate the QR code in this browser.
        </p>
      ) : (
        <div className="mt-4 flex flex-col items-center gap-3">
          {svg ? (
            <img
              src={svg}
              alt={`QR code for the public page of station ${stationCode}`}
              className="h-40 w-40 rounded-lg border border-slate-200 bg-white p-1"
              data-testid="public-qr-image"
            />
          ) : (
            <div className="flex h-40 w-40 items-center justify-center rounded-lg border border-slate-100 bg-slate-50">
              <Loader2 className="h-5 w-5 animate-spin text-cyan-600" />
            </div>
          )}

          <p className="break-all text-center text-[11px] text-slate-500" data-testid="public-qr-url">
            {publicUrl}
          </p>

          <div className="flex flex-wrap items-center justify-center gap-2">
            <a
              href={publicUrl ?? undefined}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold text-slate-700 hover:border-cyan-300 hover:text-cyan-700"
            >
              <ExternalLink className="h-3.5 w-3.5" /> Open public page
            </a>
            {svg && (
              <a
                href={svg}
                download={`hydrasense-${stationCode}-qr.svg`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-[11px] font-bold text-cyan-700 hover:bg-cyan-100"
              >
                <Download className="h-3.5 w-3.5" /> Download QR
              </a>
            )}
          </div>

          {isLocalhost && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-center text-[10px] text-amber-800">
              This URL points to localhost — it opens only on this computer. Set
              <code className="mx-1 rounded bg-amber-100 px-1 font-mono">VITE_PUBLIC_BASE_URL</code>
              to this machine&apos;s LAN or deployed address before scanning from a phone.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
