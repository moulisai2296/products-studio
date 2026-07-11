"use client";

import { useState, useEffect, useCallback } from "react";
import { api, Asset, Session } from "@/lib/api";

export default function AdminPage() {
  const [sessionIdInput, setSessionIdInput] = useState("");
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [totalCost, setTotalCost] = useState<number>(0);
  const [error, setError] = useState("");

  const fetchData = useCallback(async (id: string) => {
    const data = await api.getAdmin(id);
    setSession(data.session);
    setAssets(data.assets);
    setTotalCost(data.total_cost);
  }, []);

  const loadSession = async () => {
    if (!sessionIdInput.trim()) return;
    try {
      setError("");
      await fetchData(sessionIdInput.trim());
      setLoadedId(sessionIdInput.trim());
    } catch (err) {
      console.error(err);
      setError("Session not found");
      setLoadedId(null);
    }
  };

  // Live polling once a session is loaded — the "operations" story for judges.
  useEffect(() => {
    if (!loadedId) return;
    const interval = setInterval(() => {
      fetchData(loadedId).catch((e) => console.error(e));
    }, 3000);
    return () => clearInterval(interval);
  }, [loadedId, fetchData]);

  const setStatus = async (assetId: string, status: "approved" | "rejected") => {
    setAssets((prev) => prev.map((a) => (a.id === assetId ? { ...a, status } : a)));
    try {
      await api.updateAssetStatus(assetId, status);
      if (loadedId) await fetchData(loadedId);
    } catch (err) {
      console.error(err);
    }
  };

  const drafts = assets.filter((a) => a.status === "draft");
  const approved = assets.filter((a) => a.status === "approved");
  const rejected = assets.filter((a) => a.status === "rejected");

  const DriveStatus = ({ asset }: { asset: Asset }) => {
    if (asset.drive_status === "synced") {
      return asset.drive_url ? (
        <a
          href={asset.drive_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal font-bold hover:underline"
        >
          ✓ Synced ↗
        </a>
      ) : (
        <span className="text-teal font-bold">✓ Synced</span>
      );
    }
    if (asset.drive_status === "syncing")
      return <span className="text-marigold font-bold">⏳ Syncing</span>;
    if (asset.drive_status === "skipped")
      return <span className="text-lilac">— Skipped</span>;
    if (asset.drive_status === "failed")
      return <span className="text-rani">Failed</span>;
    return <span className="text-lilac">{asset.drive_status}</span>;
  };

  const AssetCard = ({ asset }: { asset: Asset }) => (
    <div className="bg-ink2 border border-line rounded-xl p-4 shadow-md mb-4 flex flex-col gap-3 animate-enter">
      <div className="flex justify-between items-start">
        <span className="font-bold text-sm text-ivory break-words w-2/3">{asset.label}</span>
        <span className="text-xs bg-ink px-2 py-1 rounded text-marigold border border-line whitespace-nowrap">
          ${(asset.cost_usd ?? 0).toFixed(3)}
        </span>
      </div>
      <img src={asset.url} alt={asset.label} className="w-full aspect-[4/5] object-cover rounded-lg" />
      <div className="text-xs text-lilac grid grid-cols-2 gap-y-2 mt-1 bg-ink p-3 rounded-lg border border-line">
        <div className="font-semibold text-ivory col-span-2">{asset.model}</div>
        <div>⏱ {(asset.latency_ms / 1000).toFixed(1)}s</div>
        <div className="text-right flex items-center justify-end gap-1">
          📁 <DriveStatus asset={asset} />
        </div>
      </div>
      {asset.status === "draft" && (
        <div className="flex gap-2">
          <button
            onClick={() => setStatus(asset.id, "approved")}
            className="flex-1 bg-marigold text-ink text-xs font-bold py-2 rounded-lg active:scale-95 transition"
          >
            Approve
          </button>
          <button
            onClick={() => setStatus(asset.id, "rejected")}
            className="flex-1 bg-ink text-ivory text-xs font-bold py-2 rounded-lg border border-line active:scale-95 transition"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-ink font-sans text-ivory p-8">
      <header className="mb-10 flex justify-between items-end border-b border-line pb-6">
        <div>
          <h1 className="font-display font-bold text-3xl text-marigold tracking-wide uppercase mb-2">
            Asset Review Board
          </h1>
          <p className="text-lilac">Internal campaign operations &amp; observability</p>
        </div>

        <div className="flex gap-4">
          <input
            type="text"
            value={sessionIdInput}
            onChange={(e) => setSessionIdInput(e.target.value)}
            placeholder="Enter Session ID…"
            className="bg-ink2 border border-line rounded-lg px-4 py-2 w-80 text-ivory focus:outline-none focus:border-marigold"
            onKeyDown={(e) => e.key === "Enter" && loadSession()}
          />
          <button
            onClick={loadSession}
            className="bg-marigold text-ink font-bold px-6 py-2 rounded-lg hover:opacity-90 transition"
          >
            Load
          </button>
        </div>
      </header>

      {error && <div className="text-rani mb-6 font-bold">{error}</div>}

      {session && (
        <>
          <div className="flex justify-between items-center bg-ink2 border border-line p-6 rounded-2xl mb-8">
            <div>
              <div className="text-lilac text-sm font-bold uppercase tracking-widest mb-1">
                Campaign Session
              </div>
              <div className="font-mono text-sm">{session.id}</div>
            </div>
            <div className="text-right">
              <div className="text-lilac text-sm font-bold uppercase tracking-widest mb-1">
                Total Model Spend
              </div>
              <div className="font-display text-3xl text-teal font-bold">
                ${totalCost.toFixed(3)}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-ink rounded-2xl border border-line p-5">
              <div className="flex justify-between items-center mb-6">
                <h2 className="font-display font-bold text-lg text-ivory uppercase tracking-wide">
                  Drafts
                </h2>
                <span className="bg-ink2 text-lilac font-bold px-3 py-1 rounded-full text-sm border border-line">
                  {drafts.length}
                </span>
              </div>
              <div>
                {drafts.map((asset) => (
                  <AssetCard key={asset.id} asset={asset} />
                ))}
                {drafts.length === 0 && (
                  <p className="text-lilac text-sm text-center py-8">No drafts</p>
                )}
              </div>
            </div>

            <div className="bg-ink rounded-2xl border border-teal/30 p-5">
              <div className="flex justify-between items-center mb-6">
                <h2 className="font-display font-bold text-lg text-teal uppercase tracking-wide">
                  Approved
                </h2>
                <span className="bg-teal/20 text-teal font-bold px-3 py-1 rounded-full text-sm border border-teal/30">
                  {approved.length}
                </span>
              </div>
              <div>
                {approved.map((asset) => (
                  <AssetCard key={asset.id} asset={asset} />
                ))}
                {approved.length === 0 && (
                  <p className="text-lilac text-sm text-center py-8">No approved assets</p>
                )}
              </div>
            </div>

            <div className="bg-ink rounded-2xl border border-rani/30 p-5">
              <div className="flex justify-between items-center mb-6">
                <h2 className="font-display font-bold text-lg text-rani uppercase tracking-wide">
                  Rejected
                </h2>
                <span className="bg-rani/20 text-rani font-bold px-3 py-1 rounded-full text-sm border border-rani/30">
                  {rejected.length}
                </span>
              </div>
              <div>
                {rejected.map((asset) => (
                  <AssetCard key={asset.id} asset={asset} />
                ))}
                {rejected.length === 0 && (
                  <p className="text-lilac text-sm text-center py-8">No rejected assets</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
