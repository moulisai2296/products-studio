import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-ink text-ivory font-sans flex flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl w-full text-center">
        <div className="inline-flex items-center gap-2 bg-ink2 border border-line rounded-full px-4 py-1.5 mb-8">
          <span className="text-lg">📷</span>
          <span className="text-xs font-bold tracking-widest uppercase text-lilac">
            Gemini Hackathon Build
          </span>
        </div>

        <h1 className="font-display font-extrabold text-5xl sm:text-6xl tracking-tight mb-4">
          Photo<span className="text-marigold">Dukaan</span>
        </h1>
        <p className="text-lg text-lilac leading-relaxed max-w-lg mx-auto mb-12">
          An AI photoshoot studio for Bharat&apos;s sellers. One product photo in →
          catalog angles, model shots, vernacular festive creatives, and a 10-second
          reel out — directed by conversation, published live to a storefront.
        </p>

        <div className="grid sm:grid-cols-2 gap-4 mb-10">
          <Link
            href="/studio"
            className="group bg-marigold text-ink rounded-2xl p-6 flex flex-col items-start text-left active:scale-95 transition shadow-lg"
          >
            <span className="text-2xl mb-3">💬</span>
            <span className="font-display font-bold text-lg">Studio</span>
            <span className="text-xs font-semibold opacity-80">
              Seller chat — upload, generate & approve
            </span>
          </Link>

          <Link
            href="/store"
            className="group bg-ink2 border border-line rounded-2xl p-6 flex flex-col items-start text-left active:scale-95 transition hover:border-marigold/50 opacity-90 hover:opacity-100"
          >
            <span className="text-2xl mb-3">🛍️</span>
            <span className="font-display font-bold text-lg text-ivory">Global Storefront</span>
            <span className="text-xs text-lilac">
              View all approved assets across your entire catalog.
            </span>
          </Link>
        </div>

        <p className="text-xs text-lilac">
          Start in the <Link href="/studio" className="text-marigold font-semibold hover:underline">Studio</Link> — upload a
          product photo, then watch the storefront fill live.
        </p>
      </div>
    </div>
  );
}
