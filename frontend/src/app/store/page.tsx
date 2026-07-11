"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Asset } from "@/lib/api";

interface StoreItem {
  session_id: string;
  product_name: string;
  product_folder: string;
  reel_url: string | null;
  reel_status: string;
  assets: Asset[];
  created_at: string;
}

export default function GlobalStorePage() {
  const [items, setItems] = useState<StoreItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      try {
        const data = await api.getAllStore();
        if (isMounted) {
          setItems(data.items);
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Global store poll error:", err);
      }
    };
    
    fetchData(); // Initial fetch
    const interval = setInterval(fetchData, 3000); // Poll every 3 seconds
    
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen bg-ink font-sans text-ivory">
      {/* Top Nav */}
      <header className="px-8 py-6 border-b border-line flex justify-between items-center bg-ink2 sticky top-0 z-50">
        <Link href="/" className="font-display font-bold text-2xl tracking-wide uppercase hover:opacity-80 transition">
          Photo<span className="text-marigold">Dukaan</span> Store
        </Link>
        <div className="flex gap-6 text-sm font-semibold tracking-wide">
          <span className="text-lilac">Live Catalog</span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-8 py-12">
        {isLoading ? (
          <div className="flex justify-center items-center h-64 text-lilac animate-pulse">
            Loading storefront...
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col justify-center items-center h-64 text-lilac text-center">
            <span className="text-4xl mb-4">🛍️</span>
            <p className="text-lg">No products approved yet.</p>
            <p className="text-sm mt-2 opacity-80">Head over to the Studio, upload a photo, and approve some assets to see them here.</p>
            <Link href="/studio" className="mt-6 px-6 py-2 bg-marigold text-ink rounded-full font-bold hover:scale-105 transition">
              Go to Studio
            </Link>
          </div>
        ) : (
          <div className="space-y-24">
            {items.map((item) => (
              <section key={item.session_id} className="grid grid-cols-1 lg:grid-cols-12 gap-12 border-b border-line pb-24 last:border-0">
                
                {/* Left: Product Info & Hero */}
                <div className="lg:col-span-4 flex flex-col">
                  <div className="mb-2 text-lilac font-bold tracking-widest text-xs uppercase">New Arrival</div>
                  <h2 className="font-display font-extrabold text-3xl leading-tight mb-6 capitalize">
                    {item.product_name}
                  </h2>
                  
                  <Link 
                    href={`/store/${item.session_id}`}
                    className="w-full aspect-[4/5] bg-ink2 rounded-2xl overflow-hidden border border-line shadow-2xl relative block group"
                  >
                    {item.reel_url ? (
                      <video 
                        src={item.reel_url} 
                        autoPlay 
                        loop 
                        muted 
                        playsInline
                        className="w-full h-full object-cover group-hover:scale-105 transition duration-700"
                      />
                    ) : item.assets.length > 0 ? (
                      <img
                        src={item.assets[0].url}
                        alt={item.product_name}
                        className="w-full h-full object-cover group-hover:scale-105 transition duration-700"
                      />
                    ) : null}
                    
                    <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-6">
                      <span className="text-marigold font-bold flex items-center gap-2">
                        View Details <span>→</span>
                      </span>
                    </div>
                  </Link>
                </div>

                {/* Right: Asset Grid */}
                <div className="lg:col-span-8 pt-16">
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-4">
                    {item.assets.map((asset) => (
                      <div key={asset.id} className="aspect-[4/5] rounded-xl overflow-hidden border border-line bg-ink2 shadow-md relative group">
                        <img 
                          src={asset.url} 
                          alt={asset.label} 
                          className="w-full h-full object-cover" 
                        />
                        <div className="absolute bottom-0 left-0 right-0 bg-ink/90 p-2 text-xs font-semibold text-center opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-sm border-t border-line">
                          {asset.label}
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-12 flex justify-end">
                    <button className="px-10 py-4 bg-ivory text-ink font-bold text-sm rounded-xl hover:bg-marigold transition shadow-xl uppercase tracking-wide">
                      Add {item.product_name} to Cart
                    </button>
                  </div>
                </div>

              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
