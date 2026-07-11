"use client";

import { useState, useRef, useEffect } from "react";
import { api, Asset, Session } from "@/lib/api";

export default function StudioPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [instruction, setInstruction] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Poll session state
  useEffect(() => {
    if (!sessionId) return;
    const interval = setInterval(async () => {
      try {
        const data = await api.getSession(sessionId);
        setSession(data.session);
        setAssets(data.assets);
      } catch (err) {
        console.error(err);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [assets.length, session ? session.reel_status : null, isGenerating]);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploading(true);
      const data = await api.createSession(file);
      setSessionId(data.session_id);
      
      // Start generating angles automatically
      setIsGenerating(true);
      await api.generateAngles(data.session_id);
      setIsGenerating(false);
    } catch (err) {
      console.error(err);
      setIsUploading(false);
      setIsGenerating(false);
    }
  };

  const handleEdit = async (chipText: string) => {
    if (!sessionId) return;
    try {
      // we just take the first approved or first draft as base
      const baseAsset = assets.find((a) => a.status === "approved") || assets[0];
      await api.editImage(sessionId, chipText, baseAsset?.id);
    } catch (err) {
      console.error(err);
    }
  };

  const handleApprove = async (assetId: string) => {
    try {
      await api.updateAssetStatus(assetId, "approved");
    } catch (err) {
      console.error(err);
    }
  };

  const handleReject = async (assetId: string) => {
    try {
      await api.updateAssetStatus(assetId, "rejected");
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center py-4">
      {/* Mobile Frame */}
      <div className="w-[390px] h-[844px] max-h-[95vh] bg-ink rounded-[40px] border-[8px] border-ink2 overflow-hidden shadow-2xl flex flex-col relative">
        {/* Header */}
        <header className="bg-ink2 p-2 pt-6 text-center border-b border-line shadow-sm z-10 flex-shrink-0">
          <h1 className="font-display font-bold text-lg text-marigold tracking-wide uppercase">
            PhotoDukaan
          </h1>
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
              {/* Initial Upload Message */}
              <div className="flex justify-end animate-enter">
                <div className="bg-ink2 rounded-2xl rounded-tr-sm p-3 max-w-[80%] border border-line">
                  <p className="text-sm mb-2 text-ivory">I want to sell this {session?.product_name?.toLowerCase() || 'product'}.</p>
                  {session?.product_image_url && (
                    <img 
                      src={session.product_image_url} 
                      alt="Product" 
                      className="w-full rounded-lg object-cover aspect-square"
                    />
                  )}
                </div>
              </div>

              {/* Studio Reply */}
              <div className="flex justify-start animate-enter">
                <div className="bg-line rounded-2xl rounded-tl-sm p-3 max-w-[80%] text-sm text-ivory">
                  Got it! Directing the photoshoot now. Generating 4 angles...
                </div>
              </div>

              {/* Generating Shimmer */}
              {isGenerating && (
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="aspect-[4/5] bg-ink2 rounded-xl border border-line animate-shimmer"></div>
                  ))}
                </div>
              )}

              {/* Reel Card */}
              {session?.reel_status && session.reel_status !== "pending" && (
                <div className="flex justify-start animate-enter">
                  <div className="bg-ink2 rounded-2xl p-3 border border-line w-full">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-bold text-[#7A5CD6]">Omni Flash Reel</span>
                      <span className="text-[10px] text-lilac bg-ink px-2 py-1 rounded">
                        {session.reel_status === "rendering" ? "⏳ Rendering..." : "✓ Ready"}
                      </span>
                    </div>
                    {session.reel_status === "rendering" ? (
                      <div className="w-full aspect-[4/5] bg-ink rounded-lg animate-shimmer flex items-center justify-center">
                        <span className="text-lilac text-xs">Generating video (~35s)</span>
                      </div>
                    ) : (
                      <video 
                        src={session.reel_url!} 
                        autoPlay 
                        loop 
                        muted 
                        playsInline
                        className="w-full aspect-[4/5] rounded-lg object-cover bg-black"
                      />
                    )}
                  </div>
                </div>
              )}

              {/* Assets Gallery */}
              {assets.map((asset) => (
                <div key={asset.id} className="flex justify-start animate-enter">
                  <div className="bg-ink2 rounded-2xl p-3 border border-line max-w-[90%] shadow-lg">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-bold text-ivory">{asset.label}</span>
                      <div className="flex gap-1">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
                          asset.model.includes('lite') ? 'bg-marigold text-ink' : 'bg-rani text-ivory'
                        }`}>
                          {asset.model.includes('lite') ? 'NB2 Lite' : 'NB2'}
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
              ))}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Row */}
        <div className="bg-ink2 p-2 pb-5 border-t border-line flex-shrink-0">
          {/* Quick Chips */}
          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide snap-x">
             <button 
                onClick={() => handleEdit("Show it on a model at a wedding")}
                className="snap-start shrink-0 bg-ink border border-line text-[10px] text-ivory px-3 py-1 rounded-full hover:border-marigold transition whitespace-nowrap"
             >
                ✨ Model at wedding
             </button>
             <button 
                onClick={() => handleEdit("Add 'दिवाली ऑफर 20%' text")}
                className="snap-start shrink-0 bg-ink border border-line text-[10px] text-ivory px-3 py-1 rounded-full hover:border-marigold transition whitespace-nowrap"
             >
                🪔 Diwali Offer text
             </button>
          </div>
          
          <div className="flex gap-2">
            <input 
              type="text" 
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Tell the studio what you want..."
              className="flex-1 bg-ink border border-line rounded-full px-4 py-1 text-sm text-ivory focus:outline-none focus:border-marigold placeholder-lilac"
              onKeyDown={(e) => {
                if (e.key === "Enter" && instruction) {
                  handleEdit(instruction);
                  setInstruction("");
                }
              }}
            />
            <button 
              onClick={() => {
                if (instruction) {
                  handleEdit(instruction);
                  setInstruction("");
                }
              }}
              className="w-8 h-8 rounded-full bg-marigold flex items-center justify-center shrink-0 active:scale-90 transition shadow-md"
            >
              <span className="text-ink transform rotate-[-45deg] ml-0.5 text-sm font-bold">➤</span>
            </button>
          </div>
        </div>

        {/* Home Indicator */}
        <div className="absolute bottom-1 left-1/2 transform -translate-x-1/2 w-1/3 h-1 bg-line rounded-full"></div>
      </div>
    </div>
  );
}
