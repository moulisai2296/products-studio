"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Asset } from "@/lib/api";

export default function StorePage() {
  const { sessionId } = useParams();
  const [reelUrl, setReelUrl] = useState<string | null>(null);
  const [reelStatus, setReelStatus] = useState<string>("pending");
  const [productName, setProductName] = useState<string>("");
  const [assets, setAssets] = useState<Asset[]>([]);

  // Use React hook polling pattern
  useEffect(() => {
    if (!sessionId) return;

    let isMounted = true;

    const fetchData = async () => {
      try {
        const data = await api.getStore(sessionId as string);
        if (isMounted) {
          setReelUrl(data.reel_url);
          setReelStatus(data.reel_status);
          setProductName(data.product_name);
          // Only show approved assets in the storefront
          setAssets(data.assets);
        }
      } catch (err) {
        console.error("Store poll error:", err);
      }
    };
    
    fetchData(); // Initial fetch
    const interval = setInterval(fetchData, 3000); // Poll every 3 seconds
    
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [sessionId]);

  return (
    <div className="min-h-screen bg-ink font-sans text-ivory">
      {/* Top Nav */}
      <header className="px-8 py-6 border-b border-line flex justify-between items-center bg-ink2">
        <div className="font-display font-bold text-2xl tracking-wide uppercase">
          {productName ? (
            <>
              {productName.split(" ")[0]}
              <span className="text-marigold">{productName.split(" ").slice(1).join(" ")}</span>
            </>
          ) : (
            <>Photo<span className="text-marigold">Dukaan</span></>
          )}
        </div>
        <div className="flex gap-6 text-sm font-semibold tracking-wide">
          <a href="#" className="hover:text-marigold transition">Shop</a>
          <a href="#" className="hover:text-marigold transition">Collections</a>
          <a href="#" className="hover:text-marigold transition">About</a>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-12 grid grid-cols-1 lg:grid-cols-2 gap-16">
        {/* Left Column: Media */}
        <div className="space-y-4">
          {/* Hero Media (Reel or Main Image) */}
          <div className="w-full aspect-[4/5] bg-ink2 rounded-2xl overflow-hidden border border-line shadow-2xl relative">
            {reelUrl ? (
              <video 
                src={reelUrl} 
                autoPlay 
                loop 
                muted 
                playsInline
                className="w-full h-full object-cover animate-enter"
              />
            ) : assets.length > 0 ? (
              <img
                src={assets[0].url}
                alt="Product Hero"
                className="w-full h-full object-cover animate-enter"
              />
            ) : reelStatus === "rendering" ? (
              <div className="w-full h-full flex flex-col items-center justify-center text-lilac animate-shimmer">
                <span className="text-4xl mb-4">🎬</span>
                <p>Reel is rendering…</p>
              </div>
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center text-lilac">
                <span className="text-4xl mb-4">✨</span>
                <p>Waiting for studio approvals...</p>
              </div>
            )}
          </div>

          {/* Thumbnails Gallery */}
          {assets.length > 0 && (
            <div className="grid grid-cols-4 gap-4">
              {assets.map((asset) => (
                <div key={asset.id} className="aspect-[4/5] rounded-xl overflow-hidden border border-line hover:border-marigold cursor-pointer transition animate-enter">
                  <img src={asset.url} alt={asset.label} className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column: Product Details */}
        <div className="flex flex-col pt-8">
          <div className="mb-2 text-lilac font-bold tracking-widest text-xs uppercase">PhotoDukaan Studio</div>
          <h1 className="font-display font-extrabold text-4xl leading-tight mb-4 capitalize">
            {productName || "Product"}
          </h1>
          <div className="text-2xl text-marigold font-bold mb-8">₹{Math.floor(Math.random() * 5000) + 999}</div>
          
          <p className="text-lg text-lilac leading-relaxed mb-10">
            Discover the beauty of this newly approved {productName?.toLowerCase() || "item"}. Shot and directed professionally using the PhotoDukaan Studio.
          </p>

          <button className="w-full py-5 bg-ivory text-ink font-bold text-lg rounded-xl hover:bg-marigold transition shadow-xl mb-12 uppercase tracking-wide">
            Add to Cart
          </button>

          {/* Promotional Banner Slot */}
          {assets.some(a => a.label === "Festive Offer") && (
            <div className="border border-line rounded-2xl overflow-hidden animate-enter shadow-lg">
              <img 
                src={assets.find(a => a.label === "Festive Offer")?.url} 
                alt="Festive Offer" 
                className="w-full h-auto"
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
