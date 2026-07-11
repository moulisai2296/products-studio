"""All external calls live here (models, Drive, Supabase).

Design rules (CLAUDE.md §1 & §12):
- Every function has a mock + real path; endpoints never branch on MOCK_MODE.
- Every external call is wrapped: timeout + try/except + degradation return.
  No unhandled exception can reach a screen.
- DEMO_FALLBACK=1 short-circuits generation to pre-baked seed assets.
- Langfuse span per model call (no-op when disabled).
"""
import os
import time
import asyncio
import uuid
import base64
import json
import urllib.request

import config
import observability as obs

# --- Gemini client (guarded init) -----------------------------------------
try:
    from google import genai

    gemini_client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None
except Exception as e:  # pragma: no cover - defensive
    print(f"[providers] Could not init genai client: {e}")
    gemini_client = None

# --- Supabase client (lazy, guarded) --------------------------------------
_supabase = None
_supabase_tried = False

# Mock latencies so the mock demo *feels* real.
LATENCY_LITE = 3.8
LATENCY_NB2 = 6.2
LATENCY_REEL = 6.0  # keep the mock reel snappy for rehearsals
LATENCY_DIRECTOR = 1.2
LATENCY_DRIVE = 1.2

STUDIO_HICCUP = "Studio hiccup — try that again?"


# ==========================================================================
# Helpers
# ==========================================================================
def _url_to_local_path(url: str) -> str:
    """Map a served /static/... URL back to its file on disk."""
    tail = url.split("/static/", 1)[-1]
    return os.path.join(config.STATIC_DIR, *tail.split("/"))


def _read_as_b64(url: str):
    """Read a local static file (from its URL) as (b64, mime). None on failure."""
    try:
        path = _url_to_local_path(url)
        with open(path, "rb") as f:
            data = f.read()
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return base64.b64encode(data).decode("utf-8"), mime
    except Exception as e:
        print(f"[providers] could not read hero image {url}: {e}")
        return None, None


async def _with_timeout(fn, *args, timeout: float, label: str):
    """Run a blocking fn in a thread with a hard timeout. Raises on timeout/error."""
    return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)


def _seed(name: str) -> str:
    return f"{config.SEED_URL}/{name}"

import shutil
def _copy_seed_to_draft(session: dict, seed_name: str) -> str:
    """Copies a seed image to the session's draft folder so mock mode matches real behavior."""
    draft_dir = os.path.join(config.STATIC_DIR, "assets", session["id"], "draft",
                             session.get("product_folder", "Product"))
    os.makedirs(draft_dir, exist_ok=True)
    filename = f"{session['id']}_mock_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join(draft_dir, filename)
    src_path = os.path.join(config.STATIC_DIR, "seed", seed_name)
    try:
        if os.path.exists(src_path):
            shutil.copy2(src_path, file_path)
            url_tail = os.path.relpath(file_path, config.STATIC_DIR).replace("\\", "/")
            return f"{config.PUBLIC_BASE_URL}/static/{url_tail}"
    except Exception as e:
        print(f"[providers] mock copy failed: {e}")
    return _seed(seed_name)


# ==========================================================================
# Product identification (3.5 Flash)
# ==========================================================================
def _identify_product_sync(b64_string: str, mime_type: str) -> str:
    image_part = {"inline_data": {"data": b64_string, "mime_type": mime_type}}
    res = gemini_client.models.generate_content(
        model=config.MODEL_DIRECTOR,
        contents=[
            image_part,
            "Identify the main product in this image in 1-2 words (e.g. Saree, "
            "Handbag, Watch, Shoes). Output only the product name, capitalized.",
        ],
    )
    return (res.text or "Product").strip()


async def identify_product(b64_string: str, mime_type: str) -> str:
    if config.MOCK_MODE or config.DEMO_FALLBACK:
        await asyncio.sleep(0.3)
        return "Saree"
    if not gemini_client:
        return "Product"
    try:
        with obs.generation("identify_product", model=config.MODEL_DIRECTOR):
            return await _with_timeout(
                _identify_product_sync, b64_string, mime_type,
                timeout=config.TIMEOUT_DIRECTOR, label="identify",
            )
    except Exception as e:
        print(f"[providers] identify_product failed: {e}")
        return "Product"


# ==========================================================================
# Catalog angles (NB2 Lite)
# ==========================================================================
ANGLE_SPECS = [
    {"label": "Front Drape", "seed": "angle_front.png",
     "prompt": "Professional e-commerce catalog photo of a {product}, front view, full shot, clean seamless studio background, soft lighting"},
    {"label": "Three-Quarter", "seed": "angle_34.png",
     "prompt": "Professional e-commerce catalog photo of a {product}, three-quarter angle, clean seamless studio background, soft lighting"},
    {"label": "Detail Close-up", "seed": "angle_detail.png",
     "prompt": "Professional e-commerce catalog photo of a {product}, extreme close-up on fabric detail and texture, clean background"},
    {"label": "Flat Lay", "seed": "angle_flat.png",
     "prompt": "Professional e-commerce catalog photo of a {product}, flat lay from directly above, neat folding, clean background"},
]


def _seed_angle(session: dict, spec: dict) -> dict:
    url = _copy_seed_to_draft(session, spec["seed"])
    return {
        "kind": "angle", "label": spec["label"], "url": url,
        "model": config.MODEL_ANGLE, "latency_ms": int(LATENCY_LITE * 1000),
        "cost_usd": config.COST_ANGLE, "prompt": spec["label"],
    }


def _generate_single_angle_sync(session: dict, spec: dict) -> dict:
    start = time.time()
    b64_string = session.get("product_b64")
    mime_type = session.get("mime_type", "image/jpeg")
    product = session.get("product_name", "product")
    prompt = spec["prompt"].replace("{product}", product)

    interaction = gemini_client.interactions.create(
        model=config.MODEL_ANGLE,
        input=[
            {"type": "image", "data": b64_string, "mime_type": mime_type},
            {"type": "text", "text": prompt},
        ],
        response_format={"type": "image", "aspect_ratio": "4:5", "image_size": "1K"},
    )
    image_bytes = base64.b64decode(interaction.output_image.data)

    draft_dir = os.path.join(config.STATIC_DIR, "assets", session["id"], "draft",
                             session.get("product_folder", "Product"))
    os.makedirs(draft_dir, exist_ok=True)
    filename = f"{session['id']}_angle_{uuid.uuid4().hex[:8]}.jpeg"
    file_path = os.path.join(draft_dir, filename)
    with open(file_path, "wb") as f:
        f.write(image_bytes)

    url_tail = os.path.relpath(file_path, config.STATIC_DIR).replace("\\", "/")
    return {
        "kind": "angle", "label": spec["label"],
        "url": f"{config.PUBLIC_BASE_URL}/static/{url_tail}",
        "model": config.MODEL_ANGLE, "latency_ms": int((time.time() - start) * 1000),
        "cost_usd": config.COST_ANGLE, "prompt": prompt,
    }


async def _one_angle(session: dict, spec: dict) -> dict:
    """Generate a single angle; degrade to its seed image on any failure."""
    try:
        with obs.generation("angle:" + spec["label"], model=config.MODEL_ANGLE,
                            session_id=session["id"]) as span:
            angle = await _with_timeout(
                _generate_single_angle_sync, session, spec,
                timeout=config.TIMEOUT_IMAGE, label="angle",
            )
            span.set_result(cost_usd=config.COST_ANGLE, output=angle["url"],
                            latency_ms=angle["latency_ms"])
        return angle
    except Exception as e:
        print(f"[providers] angle '{spec['label']}' failed, using seed: {e}")
        return _seed_angle(session, spec)

async def generate_angles(session: dict):
    """Always returns 4 angles. Any failing angle degrades to its seed image.

    Fires all angles CONCURRENTLY — NB2 Lite is ~4-5s/image, so the whole batch
    finishes in ~one image's time instead of the sum. gather preserves order and
    each task self-degrades, so one failure never sinks the batch.
    """
    if config.MOCK_MODE or config.DEMO_FALLBACK:
        await asyncio.sleep(LATENCY_LITE if config.MOCK_MODE else 0.2)
        return [_seed_angle(session, s) for s in ANGLE_SPECS]

    return list(await asyncio.gather(*[_one_angle(session, s) for s in ANGLE_SPECS]))


# ==========================================================================
# Conversational edit (3.5 Flash director -> NB2 chained edit)
# ==========================================================================
DIRECTOR_PROMPT = """You are a professional e-commerce photoshoot director.
The seller's instruction (may be Telugu / Hindi / Hinglish): "{instruction}"
Convert it into ONE optimized English image-editing prompt.
Hard rules:
(a) NEVER alter the product's colors, patterns, or textures.
(b) If on-image text is requested, state the EXACT text in double quotes FIRST, then instruct accurate rendering in that script.
(c) Professional e-commerce photography style.
Output ONLY the optimized prompt, no conversational filler."""


def _label_for(instruction: str) -> str:
    low = instruction.lower()
    if "wedding" in low:
        return "Model at Wedding"
    if "दिवाली" in instruction or "దీపావళి" in instruction or "offer" in low or "ऑफर" in instruction:
        return "Festive Offer"
    return "Custom Edit"


def _edit_image_sync(session: dict, instruction: str) -> dict:
    start = time.time()

    # 1) Director: seller instruction -> optimized English prompt.
    try:
        director_res = gemini_client.models.generate_content(
            model=config.MODEL_DIRECTOR,
            contents=DIRECTOR_PROMPT.format(instruction=instruction),
        )
        optimized_prompt = (director_res.text or instruction).strip()
    except Exception as e:
        print(f"[providers] director failed, using raw instruction: {e}")
        optimized_prompt = instruction

    # 2) NB2 chained edit (previous_interaction_id keeps the visual thread).
    chain_id = session.get("chain_interaction_id")
    if chain_id:
        interaction = gemini_client.interactions.create(
            model=config.MODEL_EDIT,
            input=[{"type": "text", "text": optimized_prompt}],
            previous_interaction_id=chain_id,
            response_format={"type": "image", "aspect_ratio": "4:5"},
        )
    else:
        interaction = gemini_client.interactions.create(
            model=config.MODEL_EDIT,
            input=[
                {"type": "image", "data": session.get("product_b64"),
                 "mime_type": session.get("mime_type", "image/jpeg")},
                {"type": "text", "text": optimized_prompt},
            ],
            response_format={"type": "image", "aspect_ratio": "4:5"},
        )

    image_bytes = base64.b64decode(interaction.output_image.data)
    new_chain_id = interaction.id

    draft_dir = os.path.join(config.STATIC_DIR, "assets", session["id"], "draft",
                             session.get("product_folder", "Product"))
    os.makedirs(draft_dir, exist_ok=True)
    filename = f"{session['id']}_edit_{uuid.uuid4().hex[:8]}.jpeg"
    file_path = os.path.join(draft_dir, filename)
    with open(file_path, "wb") as f:
        f.write(image_bytes)

    # FIX: build the URL from the actual saved path (was dropping the subfolders,
    # which produced a dead image URL and broke approve/Drive copy).
    url_tail = os.path.relpath(file_path, config.STATIC_DIR).replace("\\", "/")
    return {
        "ok": True, "kind": "edit", "label": _label_for(instruction),
        "url": f"{config.PUBLIC_BASE_URL}/static/{url_tail}",
        "model": config.MODEL_EDIT, "latency_ms": int((time.time() - start) * 1000),
        "cost_usd": config.COST_EDIT, "prompt": f"[Optimized] {optimized_prompt}",
        "chain_interaction_id": new_chain_id,
    }


def _seed_edit(session: dict, instruction: str) -> dict:
    label = _label_for(instruction)
    seed_file = "edit_festive_text.png" if label == "Festive Offer" else "edit_model_wedding.png"
    url = _copy_seed_to_draft(session, seed_file)
    return {
        "ok": True, "kind": "edit", "label": label, "url": url,
        "model": config.MODEL_EDIT, "latency_ms": int((LATENCY_DIRECTOR + LATENCY_NB2) * 1000),
        "cost_usd": config.COST_EDIT, "prompt": f"[Optimized] {instruction}",
        "chain_interaction_id": "seed_chain",
    }


async def edit_image(session: dict, instruction: str, base_asset_id: str = None) -> dict:
    """Returns an edit asset dict, or {'ok': False, 'message': ...} on failure."""
    if config.MOCK_MODE or config.DEMO_FALLBACK:
        await asyncio.sleep((LATENCY_DIRECTOR + LATENCY_NB2) if config.MOCK_MODE else 0.2)
        return _seed_edit(session, instruction)

    if not gemini_client:
        return {"ok": False, "message": STUDIO_HICCUP}
    try:
        with obs.generation("edit", model=config.MODEL_EDIT, session_id=session["id"],
                            inp=instruction) as span:
            result = await _with_timeout(
                _edit_image_sync, session, instruction,
                timeout=config.TIMEOUT_IMAGE, label="edit",
            )
            span.set_result(cost_usd=config.COST_EDIT, output=result["url"],
                            latency_ms=result["latency_ms"])
        return result
    except Exception as e:
        print(f"[providers] edit_image failed: {e}")
        return {"ok": False, "message": STUDIO_HICCUP}


# ==========================================================================
# Reel (Omni Flash) — image + text -> up to 10s video
# ==========================================================================
def _download_bytes(uri: str) -> bytes:
    # Try the genai SDK first (handles auth'd file URIs), then plain HTTP.
    try:
        return gemini_client.files.download(file=uri)
    except Exception:
        with urllib.request.urlopen(uri, timeout=config.TIMEOUT_VIDEO) as r:
            return r.read()


def _generate_reel_sync(session: dict, hero_b64: str, hero_mime: str) -> str:
    product = session.get("product_name", "product")
    motion = (
        f"Cinematic 10-second product reel of a {product}. Slow elegant camera "
        "push-in, soft studio lighting, gentle natural fabric movement, premium "
        "e-commerce aesthetic. Keep the product's colors and patterns exact."
    )
    interaction = gemini_client.interactions.create(
        model=config.MODEL_REEL,
        input=[
            {"type": "image", "data": hero_b64, "mime_type": hero_mime},
            {"type": "text", "text": motion},
        ],
    )
    out = interaction.output_video
    # Videos <4MB return inline base64; larger return via URI — handle both.
    data = getattr(out, "data", None)
    if data:
        mp4_bytes = base64.b64decode(data)
    else:
        uri = getattr(out, "uri", None) or getattr(out, "url", None)
        if not uri:
            raise RuntimeError("reel response had neither inline data nor uri")
        mp4_bytes = _download_bytes(uri)

    reel_dir = os.path.join(config.STATIC_DIR, "assets", session["id"])
    os.makedirs(reel_dir, exist_ok=True)
    filename = f"reel_{uuid.uuid4().hex[:8]}.mp4"
    file_path = os.path.join(reel_dir, filename)
    with open(file_path, "wb") as f:
        f.write(mp4_bytes)

    url_tail = os.path.relpath(file_path, config.STATIC_DIR).replace("\\", "/")
    return f"{config.PUBLIC_BASE_URL}/static/{url_tail}"


async def generate_reel(session: dict = None, hero_url: str = None) -> str:
    """Returns a playable reel URL. Degrades to the seed video on any failure."""
    if config.MOCK_MODE or config.DEMO_FALLBACK:
        await asyncio.sleep(LATENCY_REEL if config.MOCK_MODE else 0.2)
        return _seed("small_video.mp4")

    if not gemini_client or not session:
        return _seed("small_video.mp4")

    # Resolve the hero image (chosen angle) to base64.
    hero_b64, hero_mime = (None, None)
    if hero_url:
        hero_b64, hero_mime = _read_as_b64(hero_url)
    if not hero_b64:
        hero_b64, hero_mime = session.get("product_b64"), session.get("mime_type", "image/jpeg")
    if not hero_b64:
        return _seed("small_video.mp4")

    try:
        with obs.generation("reel", model=config.MODEL_REEL, session_id=session["id"]) as span:
            url = await _with_timeout(
                _generate_reel_sync, session, hero_b64, hero_mime,
                timeout=config.TIMEOUT_VIDEO, label="reel",
            )
            span.set_result(cost_usd=config.COST_REEL_PER_SEC * config.REEL_SECONDS, output=url)
        return url
    except Exception as e:
        print(f"[providers] generate_reel failed, using seed: {e}")
        return _seed("small_video.mp4")


# ==========================================================================
# Google Drive (background nicety — never surfaces to the seller UI)
# ==========================================================================
def _load_service_account_info():
    """Accept either inline JSON or a path to the service-account file."""
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        return None
    raw = raw.strip()
    if os.path.exists(raw):
        with open(raw, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(raw)


def _get_or_create_folder(service, name: str, parent_id: str) -> str:
    q = (f"name='{name}' and '{parent_id}' in parents and "
         "mimeType='application/vnd.google-apps.folder' and trashed=false")
    items = service.files().list(q=q, spaces="drive", fields="files(id,name)").execute().get("files", [])
    if items:
        return items[0]["id"]
    meta = {"name": name, "parents": [parent_id], "mimeType": "application/vnd.google-apps.folder"}
    return service.files().create(body=meta, fields="id").execute()["id"]


def _sync_asset_sync(session: dict, folder_type: str, asset: dict):
    if not config.DRIVE_PARENT_FOLDER_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return None, "skipped"
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_info(
            _load_service_account_info(), scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        session_folder = _get_or_create_folder(service, session["id"], config.DRIVE_PARENT_FOLDER_ID)
        sub_folder = _get_or_create_folder(service, folder_type, session_folder)
        product_folder = _get_or_create_folder(
            service, session.get("product_folder", "Product"), sub_folder)

        local_path = _url_to_local_path(asset["url"])
        if not os.path.exists(local_path):
            print(f"[providers] drive: local file missing {local_path}")
            return None, "failed"

        media = MediaFileUpload(local_path, resumable=True)
        meta = {"name": os.path.basename(local_path), "parents": [product_folder]}
        uploaded = service.files().create(body=meta, media_body=media, fields="id").execute()
        return uploaded.get("id"), "synced"
    except Exception as e:
        print(f"[providers] drive upload failed: {e}")
        return None, "failed"


async def sync_asset_to_drive(session: dict, folder_type: str, asset: dict):
    if config.MOCK_MODE:
        await asyncio.sleep(LATENCY_DRIVE)
        return "mock_drive_file_id", "synced"
    if config.DEMO_FALLBACK:
        return None, "skipped"
    try:
        return await _with_timeout(
            _sync_asset_sync, session, folder_type, asset,
            timeout=config.TIMEOUT_DRIVE, label="drive",
        )
    except Exception as e:
        print(f"[providers] drive sync timed out/failed: {e}")
        return None, "failed"


# ==========================================================================
# Supabase (persistence mirror — in-memory store stays source of truth)
# ==========================================================================
_SESSION_COLS = ("id", "product_image_url", "product_name", "product_folder",
                 "chain_interaction_id", "reel_status", "reel_url",
                 "reel_seed_asset_id", "created_at")
_ASSET_COLS = ("id", "session_id", "kind", "label", "status", "url", "model",
               "latency_ms", "cost_usd", "drive_file_id", "drive_url",
               "drive_status", "prompt", "created_at")


def drive_url_for(file_id: str) -> str:
    """Build a clickable Drive link from a file id."""
    return f"https://drive.google.com/file/d/{file_id}/view" if file_id else None


def _get_supabase():
    global _supabase, _supabase_tried
    if config.MOCK_MODE:
        return None
    if _supabase_tried:
        return _supabase
    _supabase_tried = True
    if not (config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY):
        return None
    try:
        from supabase import create_client
        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        print("[providers] supabase client initialized")
    except Exception as e:  # pragma: no cover
        print(f"[providers] supabase init failed, using memory only: {e}")
        _supabase = None
    return _supabase


def db_available() -> bool:
    return _get_supabase() is not None


def _pick(row: dict, cols) -> dict:
    return {k: row.get(k) for k in cols if k in row}


def _upsert_sync(table: str, row: dict, cols):
    client = _get_supabase()
    if client is None:
        return False
    try:
        client.table(table).upsert(_pick(row, cols)).execute()
        return True
    except Exception as e:
        print(f"[providers] supabase upsert {table} failed (using memory): {e}")
        return False


async def db_upsert_session(session: dict):
    if _get_supabase() is None:
        return
    try:
        await _with_timeout(_upsert_sync, "sessions", session, _SESSION_COLS,
                            timeout=config.TIMEOUT_SUPABASE, label="db_session")
    except Exception as e:
        print(f"[providers] db_upsert_session failed: {e}")


async def db_upsert_asset(asset: dict):
    if _get_supabase() is None:
        return
    try:
        await _with_timeout(_upsert_sync, "assets", asset, _ASSET_COLS,
                            timeout=config.TIMEOUT_SUPABASE, label="db_asset")
    except Exception as e:
        print(f"[providers] db_upsert_asset failed: {e}")
