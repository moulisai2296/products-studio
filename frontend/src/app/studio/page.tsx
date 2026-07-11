"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { api, Asset, Session } from "@/lib/api";

type ChatMsg = {
  id: string;
  ts: number;
  role: "seller" | "studio";
  text?: string;
  pending?: boolean;
  reanimateAssetId?: string;
};

const uid = () => Math.random().toString(36).slice(2);

export default function StudioPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [instruction, setInstruction] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Poll session state.
  useEffect(() => {
    if (!sessionId) return;
    const tick = async () => {
      try {
        const data = await api.getSession(sessionId);
        setSession(data.session);
        setAssets(data.assets);
      } catch (err) {
        console.error(err);
      }
    };
    tick();
    const interval = setInterval(tick, 2000);
    return () => clearInterval(interval);
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [assets.length, messages.length, session?.reel_status, isGenerating]);

  const pushMsg = (m: Omit<ChatMsg, "id" | "ts"> & Partial<Pick<ChatMsg, "id" | "ts">>) => {
    const msg: ChatMsg = { id: m.id ?? uid(), ts: m.ts ?? Date.now(), ...m } as ChatMsg;
    setMessages((prev) => [...prev, msg]);
    return msg.id;
  };
  const removeMsg = (id: string) => setMessages((prev) => prev.filter((m) => m.id !== id));

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsUploading(true);
      const data = await api.createSession(file);
      setSessionId(data.session_id);
      setIsGenerating(true);
      await api.generateAngles(data.session_id);
      setIsGenerating(false);
    } catch (err) {
      console.error(err);
      setIsUploading(false);
      setIsGenerating(false);
      pushMsg({ role: "studio", text: "Couldn't reach the studio — try uploading again?" });
    }
  };

  const runEdit = async (text: string) => {
    if (!sessionId || !text.trim()) return;
    pushMsg({ role: "seller", text });
    const pendingId = pushMsg({ role: "studio", pending: true });
    try {
      const baseAsset = assets.find((a) => a.status === "approved") || assets[0];
      const res = await api.editImage(sessionId, text, baseAsset?.id);
      removeMsg(pendingId);
      if (!res.asset && res.message) {
        pushMsg({ role: "studio", text: res.message });
      }
      // On success the new asset arrives via polling and slots in by time.
    } catch (err) {
      console.error(err);
      removeMsg(pendingId);
      pushMsg({ role: "studio", text: "Studio hiccup — try that again?" });
    }
  };

  const handleApprove = async (assetId: string) => {
    // Optimistic: flip status locally right away.
    setAssets((prev) => prev.map((a) => (a.id === assetId ? { ...a, status: "approved" } : a)));
    try {
      const res = await api.updateAssetStatus(assetId, "approved");
      if (res.reanimate_hint) {
        pushMsg({ role: "studio", text: "Love this shot! Animate it with Omni Flash?", reanimateAssetId: assetId });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleReject = async (assetId: string) => {
    setAssets((prev) => prev.map((a) => (a.id === assetId ? { ...a, status: "rejected" } : a)));
    try {
      await api.updateAssetStatus(assetId, "rejected");
    } catch (err) {
      console.error(err);
    }
  };

  const handleReanimate = async (assetId: string, msgId: string) => {
    removeMsg(msgId);
    if (!sessionId) return;
    try {
      await api.animate(sessionId, assetId);
    } catch (err) {
      console.error(err);
    }
  };

  const handleApproveReel = async () => {
    if (!sessionId) return;
    setSession((prev) => prev ? { ...prev, reel_status: "approved" } : null);
    try {
      await api.approveReel(sessionId);
    } catch (err) {
      console.error(err);
    }
  };

  // Merge chat messages + asset cards into one time-ordered timeline.
  const timeline = useMemo(() => {
    const items: { ts: number; render: React.ReactNode; key: string }[] = [];
    for (const m of messages) {
      items.push({ ts: m.ts, key: `m-${m.id}`, render: renderMessage(m) });
    }
    
    // Group angles into a single grid
    const angles = assets.filter((a) => a.kind === "angle");
    if (angles.length > 0) {
      items.push({
        ts: Date.parse(angles[0].created_at) || 0,
        key: "angles-grid",
        render: (
          <div className="grid grid-cols-2 gap-2 mt-2">
            {angles.map((asset) => renderGridAsset(asset))}
          </div>
        ),
      });
    }

    // Render edits individually
    const edits = assets.filter((a) => a.kind === "edit");
    for (const a of edits) {
      items.push({ ts: Date.parse(a.created_at) || 0, key: `a-${a.id}`, render: renderAsset(a) });
    }
    
    items.sort((x, y) => x.ts - y.ts);
    return items;
  }, [messages, assets]);

  function renderMessage(m: ChatMsg) {
    if (m.role === "seller") {
      return (
        <div className="flex justify-end animate-enter">
          <div className="bg-ink2 rounded-2xl rounded-tr-sm p-3 max-w-[80%] border border-line text-sm text-ivory">
            {m.text}
          </div>
        </div>
      );
    }
    if (m.pending) {
      return (
        <div className="flex justify-start animate-enter">
          <div className="bg-ink2 rounded-2xl p-3 border border-line w-[70%]">
            <div className="text-[10px] text-lilac mb-2">Studio is editing…</div>
            <div className="aspect-[4/5] bg-ink rounded-lg animate-shimmer" />
          </div>
        </div>
      );
    }
    return (
      <div className="flex justify-start animate-enter">
        <div className="bg-line rounded-2xl rounded-tl-sm p-3 max-w-[85%] text-sm text-ivory">
          <p>{m.text}</p>
          {m.reanimateAssetId && (
            <button
              onClick={() => handleReanimate(m.reanimateAssetId!, m.id)}
              className="mt-2 bg-[#7A5CD6] text-ivory text-xs font-bold px-3 py-1.5 rounded-full active:scale-95 transition"
            >
              🎬 Animate this shot
            </button>
          )}
        </div>
      </div>
    );
  }

  function renderAsset(asset: Asset) {
    const isLite = asset.model.includes("lite");
    return (
      <div className="flex justify-start animate-enter">
        <div className="bg-ink2 rounded-2xl p-3 border border-line max-w-[90%] shadow-lg">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs font-bold text-ivory">{asset.label}</span>
            <div className="flex gap-1">
              <span
                className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
                  isLite ? "bg-marigold text-ink" : "bg-rani text-ivory"
                }`}
              >
                {isLite ? "NB2 Lite" : "NB2"}
              </span>
              <span className="text-[9px] text-lilac bg-ink px-1.5 py-0.5 rounded border border-line">
                {(asset.latency_ms / 1000).toFixed(1)}s
              </span>
            </div>
          </div>
          <img
            src={asset.url}
            alt={asset.label}
            className="w-full rounded-lg aspect-[4/5] object-cover mb-3"
          />
          <div className="flex gap-2">
            {asset.status === "approved" ? (
              <div className="flex-1 text-center py-2 text-xs font-bold text-teal bg-ink rounded-lg border border-teal/30">
                ✓ Approved
              </div>
            ) : asset.status === "rejected" ? (
              <div className="flex-1 text-center py-2 text-xs font-bold text-rani bg-ink rounded-lg border border-rani/30">
                ✕ Rejected
              </div>
            ) : (
              <>
                <button
                  onClick={() => handleApprove(asset.id)}
                  className="flex-1 bg-marigold text-ink text-xs font-bold py-2 rounded-lg active:scale-95 transition"
                >
                  Approve
                </button>
                <button
                  onClick={() => handleReject(asset.id)}
                  className="flex-1 bg-ink text-ivory text-xs font-bold py-2 rounded-lg border border-line active:scale-95 transition"
                >
                  Reject
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  function renderGridAsset(asset: Asset) {
    const isLite = asset.model.includes("lite");
    return (
      <div key={asset.id} className="bg-ink2 rounded-xl p-2 border border-line flex flex-col shadow-lg animate-enter">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-[10px] font-bold text-ivory truncate pr-1">{asset.label}</span>
          <span className="text-[8px] text-lilac bg-ink px-1 rounded border border-line shrink-0">
            {(asset.latency_ms / 1000).toFixed(1)}s
          </span>
        </div>
        <img
          src={asset.url}
          alt={asset.label}
          className="w-full rounded-lg aspect-[4/5] object-cover mb-2"
        />
        <div className="flex gap-1 mt-auto">
          {asset.status === "approved" ? (
            <div className="flex-1 text-center py-1.5 text-[10px] font-bold text-teal bg-ink rounded-md border border-teal/30">
              ✓ Appr
            </div>
          ) : asset.status === "rejected" ? (
            <div className="flex-1 text-center py-1.5 text-[10px] font-bold text-rani bg-ink rounded-md border border-rani/30">
              ✕ Rej
            </div>
          ) : (
            <>
              <button
                onClick={() => handleApprove(asset.id)}
                className="flex-1 bg-marigold text-ink text-[10px] font-bold py-1.5 rounded-md active:scale-95 transition"
              >
                Approve
              </button>
              <button
                onClick={() => handleReject(asset.id)}
                className="flex-1 bg-ink text-ivory text-[10px] font-bold py-1.5 rounded-md border border-line active:scale-95 transition"
              >
                Reject
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  const chips: { emoji: string; label: string; text: string }[] = [
    { emoji: "🪔", label: "Telugu offer", text: "Add 'దీపావళి ఆఫర్ 20%' text" },
    { emoji: "🎁", label: "Hindi offer", text: "Add 'दिवाली ऑफर 20%' text" },
    { emoji: "✨", label: "Model at wedding", text: "Show it on a model at a wedding" },
    { emoji: "🌸", label: "Festive background", text: "Place it on a festive Diwali background with marigolds" },
  ];

  return (
    <div className="min-h-screen bg-black flex items-center justify-center py-4">
      {/* Mobile Frame */}
      <div className="w-[390px] h-[844px] max-h-[95vh] bg-ink rounded-[40px] border-[8px] border-ink2 overflow-hidden shadow-2xl flex flex-col relative">
        {/* Header */}
        <header className="bg-ink2 p-2 pt-6 text-center border-b border-line shadow-sm z-10 flex-shrink-0">
          <h1 className="font-display font-bold text-lg text-marigold tracking-wide uppercase">
            PhotoDukaan
          </h1>
          {session?.product_name && (
            <p className="text-[10px] text-lilac">{session.product_name} · studio session</p>
          )}
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6 bg-ink flex flex-col scroll-smooth">
          {!sessionId && (
            <div className="m-auto text-center space-y-4">
              <div className="w-20 h-20 bg-ink2 rounded-full mx-auto flex items-center justify-center border border-line">
                <span className="text-3xl">📷</span>
              </div>
              <div>
                <h2 className="text-ivory font-display font-semibold text-lg mb-1">
                  Start a Photoshoot
                </h2>
                <p className="text-lilac text-sm mb-6 max-w-[250px] mx-auto">
                  Upload a single photo of your product to generate catalog angles,
                  reels, and festive promos.
                </p>
                <button
                  onClick={handleUploadClick}
                  disabled={isUploading}
                  className="bg-marigold text-ink font-bold py-3 px-8 rounded-full shadow-lg active:scale-95 transition disabled:opacity-50"
                >
                  {isUploading ? "Uploading..." : "Upload Photo"}
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept="image/*"
                  onChange={handleFileChange}
                />
              </div>
            </div>
          )}

          {sessionId && (
            <>
              {/* Initial upload bubble */}
              <div className="flex justify-end animate-enter">
                <div className="bg-ink2 rounded-2xl rounded-tr-sm p-3 max-w-[80%] border border-line">
                  <p className="text-sm mb-2 text-ivory">
                    I want to sell this {session?.product_name?.toLowerCase() || "product"}.
                  </p>
                  {session?.product_image_url && (
                    <img
                      src={session.product_image_url}
                      alt="Product"
                      className="w-full rounded-lg object-cover aspect-square"
                    />
                  )}
                </div>
              </div>

              {/* Studio reply */}
              <div className="flex justify-start animate-enter">
                <div className="bg-line rounded-2xl rounded-tl-sm p-3 max-w-[80%] text-sm text-ivory">
                  Got it! Directing the photoshoot now. Generating 4 angles…
                </div>
              </div>

              {/* Angle shimmer while first batch generates */}
              {isGenerating && assets.length === 0 && (
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="aspect-[4/5] bg-ink2 rounded-xl border border-line animate-shimmer"
                    />
                  ))}
                </div>
              )}

              {/* Time-ordered timeline: seller bubbles, studio messages, asset cards */}
              {timeline.map((item) => (
                <div key={item.key}>{item.render}</div>
              ))}

              {/* Reel card (shown at the bottom once triggered by an approval) */}
              {session?.reel_seed_asset_id && (
                <div className="flex justify-start animate-enter mt-4">
                  <div className="bg-ink2 rounded-2xl p-3 border border-line w-full">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-bold text-[#7A5CD6]">Omni Flash Reel</span>
                      <span className="text-[10px] text-lilac bg-ink px-2 py-1 rounded">
                        {session.reel_status === "rendering"
                          ? "⏳ Rendering…"
                          : session.reel_status === "failed"
                          ? "Retry soon"
                          : session.reel_status === "approved"
                          ? "✓ Published"
                          : "✓ Ready"}
                      </span>
                    </div>
                    {(session.reel_status === "ready" || session.reel_status === "approved") && session.reel_url ? (
                      <div className="flex flex-col gap-3">
                        <video
                          src={session.reel_url}
                          autoPlay
                          loop
                          muted
                          playsInline
                          className="w-full aspect-[4/5] rounded-lg object-cover bg-black"
                        />
                        {session.reel_status === "ready" ? (
                          <button
                            onClick={handleApproveReel}
                            className="w-full bg-[#7A5CD6] text-ivory text-xs font-bold py-2.5 rounded-lg active:scale-95 transition shadow-md"
                          >
                            Approve Video to Publish
                          </button>
                        ) : (
                          <div className="w-full text-center py-2.5 text-xs font-bold text-teal bg-ink rounded-lg border border-teal/30">
                            ✓ Published to Storefront
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="w-full aspect-[4/5] bg-ink rounded-lg animate-shimmer flex items-center justify-center">
                        <span className="text-lilac text-xs">
                          {session.reel_status === "failed"
                            ? "Reel will retry"
                            : "Omni Flash is rendering…"}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Row */}
        <div className="bg-ink2 p-2 pb-5 border-t border-line flex-shrink-0">
          {/* Quick chips */}
          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide snap-x">
            {chips.map((c) => (
              <button
                key={c.label}
                onClick={() => runEdit(c.text)}
                disabled={!sessionId}
                className="snap-start shrink-0 bg-ink border border-line text-[10px] text-ivory px-3 py-1 rounded-full hover:border-marigold transition whitespace-nowrap disabled:opacity-40"
              >
                {c.emoji} {c.label}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Tell the studio what you want…"
              className="flex-1 bg-ink border border-line rounded-full px-4 py-1 text-sm text-ivory focus:outline-none focus:border-marigold placeholder-lilac"
              onKeyDown={(e) => {
                if (e.key === "Enter" && instruction.trim()) {
                  runEdit(instruction);
                  setInstruction("");
                }
              }}
            />
            <button
              onClick={() => {
                if (instruction.trim()) {
                  runEdit(instruction);
                  setInstruction("");
                }
              }}
              className="w-8 h-8 rounded-full bg-marigold flex items-center justify-center shrink-0 active:scale-90 transition shadow-md"
            >
              <span className="text-ink transform rotate-[-45deg] ml-0.5 text-sm font-bold">➤</span>
            </button>
          </div>
        </div>

        {/* Home indicator */}
        <div className="absolute bottom-1 left-1/2 transform -translate-x-1/2 w-1/3 h-1 bg-line rounded-full" />
      </div>
    </div>
  );
}
