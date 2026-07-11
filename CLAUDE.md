# CLAUDE.md — PhotoDukaan (repo: product_studio)

AI photoshoot studio for Bharat's sellers. One product photo in → catalog angles,
model shots, vernacular festive creatives, and a 10-second reel out — directed by
conversation in the seller's own language, published live to a storefront.

Hackathon build (Google Gemini hackathon, judged on live demo). **The prime
directive: the demo flow must NEVER break.** Every feature decision defers to that.

---

## 1. Prime directive: zero-breakage design

1. **MOCK_MODE first.** Every model/Drive/Supabase call sits behind a provider
   function with a mock implementation. `MOCK_MODE=1` runs the entire app with
   zero external dependencies (SVG placeholder images, fake latencies, in-memory
   store). Build and verify every feature in mock first, then flip real.
2. **Graceful degradation, never crash.** Every external call is wrapped:
   - Model call fails → return the most recent good asset for that slot + a
     polite chat message ("Studio hiccup — try that again?"). Never a stack trace,
     never a frozen spinner.
   - Supabase unreachable → fall back to the in-memory session store silently.
   - Drive unreachable → skip sync, log to Langfuse, continue. Drive is a
     background nicety, not a dependency.
   - Langfuse unreachable → no-op. Observability must never take down the app.
3. **The chat is never blocked.** Anything slower than ~10s (Omni Flash reel,
   Drive sync) runs in FastAPI BackgroundTasks. The UI shows progress states,
   not blank waits.
4. **Timeouts everywhere:** 30s on image calls, 120s on video, 10s on Drive and
   Supabase. On timeout → degradation path above.
5. **Demo fallback:** a `seed/` directory with pre-generated real outputs
   (angles, edited shots, one reel MP4). A `DEMO_FALLBACK=1` env flag serves
   these if the venue network dies mid-demo.

---

## 2. Tech stack (locked — do not add anything)

| Layer | Tech | Role |
|---|---|---|
| Frontend | Next.js 14+ (App Router), Tailwind | 3 screens (below) |
| Backend | Python FastAPI, single service | All model orchestration, Drive, Supabase writes |
| Models | google-genai SDK → Gemini Interactions API | 3.5 Flash, NB2 Lite, NB2, Omni Flash |
| Storage | Supabase (Postgres) | sessions + assets tables. No auth, no RLS, service key from backend only |
| Assets | Google Drive API (service account) | Drafts/ and Approved/ folders per session |
| Observability | Langfuse (Python SDK) | trace per session, span per model call, cost tracking |

**Forbidden:** user OAuth flows, Redis, queues, websockets (poll instead),
extra microservices, auth of any kind, payment anything. Frontend NEVER calls
Google/Supabase/Langfuse directly — everything goes through FastAPI.

---

## 3. Verified model facts (checked against ai.google.dev, July 2026 — trust these)

| Purpose | Model string | Notes |
|---|---|---|
| Director (text) | `gemini-3.5-flash` | GA/stable. Keep DEFAULT temperature (Gemini 3.x guidance: don't tune it) |
| Catalog angles | `gemini-3.1-flash-lite-image` (NB2 Lite) | ~4s/image, ~$0.034/image at 1K. Single-shot generation only — NOT optimized for multi-turn editing or multiple reference inputs. `image_size: "1K"` is the only size it supports |
| Conversational edits | `gemini-3.1-flash-image` (NB2) | Reliable text rendering. Multi-turn editing via `previous_interaction_id` is the docs-recommended pattern (up to ~3 stacked edits work well) |
| Reel | `gemini-omni-flash-preview` (Omni Flash) | Image+text → up to 10s video. Takes 30–60s+. Videos <4MB return inline base64; larger return via URI — handle both |

API pattern (Interactions API):

```python
from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Image (angles: model=NB2 Lite; edits: model=NB2)
interaction = client.interactions.create(
    model=MODEL,
    input=[
        {"type": "image", "data": b64_string, "mime_type": "image/jpeg"},
        {"type": "text", "text": prompt},
    ],
    response_format={"type": "image", "aspect_ratio": "4:5", "image_size": "1K"},
)
image_b64 = interaction.output_image.data
chain_id = interaction.id   # store for multi-turn

# Follow-up edit in the same visual thread — send ONLY text + previous id:
interaction = client.interactions.create(
    model="gemini-3.1-flash-image",
    input=[{"type": "text", "text": next_prompt}],
    previous_interaction_id=chain_id,
    response_format={"type": "image", "aspect_ratio": "4:5"},
)

# Video (background task)
interaction = client.interactions.create(
    model="gemini-omni-flash-preview",
    input=[
        {"type": "image", "data": hero_b64, "mime_type": "image/png"},
        {"type": "text", "text": motion_prompt},
    ],
)
mp4_bytes = base64.b64decode(interaction.output_video.data)
```

If the SDK surface differs slightly at runtime (field naming drift), check the
actual response object and adapt — but the model strings and the
previous_interaction_id pattern are verified. Do not invent other model names.

**Director prompt rules (3.5 Flash):** convert the seller's Telugu/Hindi/Hinglish
instruction into ONE optimized English image-editing prompt. Hard rules inside
the system prompt: (a) never alter the product's colors/patterns/textures;
(b) if on-image text is requested, state the exact text in double quotes FIRST,
then instruct accurate rendering in that script (docs-recommended technique);
(c) professional e-commerce photography style.

**Language risk:** Telugu is NOT on the image models' best-performance list
(Hindi hi-IN is). Test Telugu on-image text first with the real key. Keep a
Hindi quick-chip ("दिवाली ऑफर 20%") as the guaranteed demo path.

---

## 4. User flow (the demo script IS the spec)

1. **Upload** (mobile chat screen): seller uploads one product photo → session created.
2. **Contact sheet:** 4 NB2 Lite calls (front / three-quarter / detail close-up /
   flat lay) stream into the chat one by one as they finish, each with a latency
   + model badge ("3.8s · NB2 Lite"). Simultaneously, BackgroundTasks start:
   (a) Omni Flash reel from the front angle, (b) Drive Drafts/ sync.
3. **Direct & edit:** seller types/taps chips ("Show it on a model at a wedding",
   "Add 'దీపావళి ఆఫర్ 20%' text", Hindi backup chip). 3.5 Flash rewrites → NB2
   chained edit → result renders inline with Approve / Reject buttons.
4. **Approve:** asset status → approved in Supabase; background copy to Drive
   Approved/; if approved hero ≠ reel seed, chat offers "Re-animate from this shot?"
5. **Storefront:** product page (separate route) polls approved assets — gallery
   fills live, reel autoplays as hero. Demo close: cut from chat to storefront.

---

## 5. Screens (Next.js) — 3 routes

### 5.1 `/studio` — Seller chat (MOBILE-FRAMED)
Rendered inside a phone frame (~390px) centered on desktop — judges see "this is
Lakshmi's phone." Chat thread: seller bubbles right, studio replies left,
generated images as inline cards with Approve (marigold) / Reject / Edit buttons
and latency+model badge. Quick-chips above the input (Telugu text, Hindi text,
model-at-wedding, festive background). Reel card shows shimmer + "Omni Flash is
rendering…" then autoplays. Input row: text field + send; mic icon can be
non-functional decoration.

### 5.2 `/store/[sessionId]` — Product page (DESKTOP)
Polished e-commerce product page: reel as hero media (autoplay loop, muted),
approved images as thumbnail gallery, product title/price (mock data), the
vernacular festive creative in a promo banner slot. Polls `/api/store/{id}`
every 3s; new approvals animate in. No cart/checkout — one page, done beautifully.

### 5.3 `/admin` — Asset review board (DESKTOP)
Three-column board: Drafts / Approved / Rejected. Cards show thumbnail, model
used, latency, cost estimate, Drive sync status (✓ synced / ⏳ syncing / — skipped).
Data from Supabase via `/api/admin/{sessionId}`. Approve/Reject also possible
here (same endpoint as chat). This is the "operations" story for judges.

### Design system (use EXACTLY these tokens)
```
--ink:      #201A3A   (page background)
--ink2:     #2B2450   (cards, surfaces)
--line:     #3a3168   (borders)
--marigold: #F5A83C   (primary actions, badges, accents)
--rani:     #D64570   (secondary accent, NB2 chip)
--ivory:    #F8F4EA   (text)
--lilac:    #A79FC7   (muted text)
--teal:     #4FC3B0   (director/3.5 Flash chip, success)
```
Fonts (Google Fonts): **Bricolage Grotesque** for display/headings,
**Sora** for body/UI. Dark studio aesthetic throughout — the app looks like a
photo studio, not a SaaS dashboard.

UX rules: every model call gets a skeleton/shimmer state; images animate in
(fade+scale, respect prefers-reduced-motion); optimistic approve (instant UI,
background persist); errors are friendly chat messages; never a raw spinner
with no words; never a layout shift when images land (reserve 4:5 slots).

---

## 6. Data model (Supabase — keep to exactly 2 tables)

```sql
create table sessions (
  id text primary key,
  product_image_url text,          -- Supabase storage or data URI
  chain_interaction_id text,       -- NB2 multi-turn chain pointer
  reel_status text default 'pending',  -- pending|rendering|ready|failed
  reel_url text,
  reel_seed_asset_id text,
  created_at timestamptz default now()
);

create table assets (
  id text primary key,
  session_id text references sessions(id),
  kind text,                       -- angle|edit|reel
  label text,                      -- "Front, clean studio" or the instruction
  status text default 'draft',     -- draft|approved|rejected
  url text,                        -- served image/video URL
  model text,                      -- gemini-3.1-flash-lite-image etc.
  latency_ms int,
  cost_usd numeric,
  drive_file_id text,
  drive_status text default 'pending',  -- pending|synced|skipped
  prompt text,                     -- the final optimized prompt used
  created_at timestamptz default now()
);
```
No RLS, no auth, backend uses the service key. If Supabase is down, an
in-memory dict mirrors this shape — the app must run identically.

Generated images: store as files under FastAPI `static/assets/` and serve by
URL (simplest); Supabase Storage only if trivially quick.

---

## 7. Langfuse (observability — thin, decorator-based)

- One **trace per session** (trace_id = session_id).
- One **generation span per model call** with: model name, latency, and cost.
- Cost table (hardcode): NB2 Lite image $0.034 · NB2 image $0.067 (verify at
  runtime if listed, else use this) · Omni Flash $0.10/second (≈$1.00 per 10s
  reel) · 3.5 Flash token pricing (log tokens, cost optional).
- Use `@observe` decorators / context managers around the provider functions.
- `LANGFUSE_ENABLED=0` must cleanly no-op everything.
- Judge story: open the Langfuse dashboard on the admin screen or a browser tab
  — "every rupee of model spend per campaign, live." Total campaign cost badge
  on the admin screen sums `cost_usd` from assets.

---

## 8. Google Drive (background nicety)

Service account JSON via `GOOGLE_SERVICE_ACCOUNT_JSON` env (path or inline).
One pre-shared parent folder (`DRIVE_PARENT_FOLDER_ID`). Per session create
`{session_id}/Drafts/` and `{session_id}/Approved/`. Push drafts on generation,
copy to Approved on approval — all in BackgroundTasks. Update
`assets.drive_status`. NEVER let Drive failures surface to the seller UI.

---

## 9. API endpoints (FastAPI)

```
POST /api/session                  multipart photo → {session_id}
POST /api/generate-angles          {session_id} → streams/returns 4 assets; enqueues reel + Drive
POST /api/edit                     {session_id, instruction, base_asset_id?} → 1 asset
POST /api/assets/{id}/status       {status: approved|rejected} → updates + Drive copy + re-animate hint
POST /api/animate                  {session_id, asset_id} → kicks background reel; poll session for status
GET  /api/session/{id}             full session state (chat screen polls this)
GET  /api/store/{id}               approved assets + reel (storefront polls, 3s)
GET  /api/admin/{id}               all assets with model/latency/cost/drive fields
```
CORS open. Next.js talks only to these.

---

## 10. Build order (phases — finish each before the next)

- **Phase 0 (scaffold):** FastAPI + Next.js monorepo (`backend/`, `frontend/`),
  MOCK_MODE providers, in-memory store. All 3 screens render with mock data
  end-to-end. ← This alone is a demoable app.
- **Phase 1 (real images):** wire NB2 Lite angles + 3.5 Flash director + NB2
  chained edits. Test Telugu text; decide Telugu vs Hindi chip.
- **Phase 2 (reel):** Omni Flash background task + storefront hero.
- **Phase 3 (persistence):** Supabase mirror + admin screen live data.
- **Phase 4 (extras):** Drive sync, Langfuse, cost badges.
- **Phase 5 (polish):** transitions, seed/ fallback assets, rehearse.

**Cut order if time slips (cut from the bottom):** Langfuse dashboard → Drive
(show pre-populated folder, narrate) → admin screen (storefront can carry the
approval story). NEVER cut: chat + angles + edits + storefront.

---

## 11. Env vars

```
MOCK_MODE=1                      # flip to 0 with real key
DEMO_FALLBACK=0                  # 1 = serve seed/ assets (network-death insurance)
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GOOGLE_SERVICE_ACCOUNT_JSON=     # path to service account file
DRIVE_PARENT_FOLDER_ID=
LANGFUSE_ENABLED=0
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## 12. Conventions

- Python: type hints, one `providers.py` for all external calls (models, Drive,
  Supabase) with mock/real switch inside each function — endpoints never branch
  on MOCK_MODE themselves.
- Next.js: App Router, server components where possible, one `api.ts` client,
  Tailwind with the tokens above as CSS variables. No component libraries —
  hand-rolled to match the design system.
- Every provider function: try/except + timeout + Langfuse span + degradation
  return. No unhandled exceptions can reach a screen.
- Commit after every phase. Keep `seed/` assets out of .gitignore.
