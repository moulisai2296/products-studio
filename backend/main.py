"""PhotoDukaan FastAPI service.

The in-memory dicts are the source of truth (always fast, never down). Every
write is also mirrored to Supabase in a BackgroundTask — if Supabase is
unreachable the app runs identically on memory alone (CLAUDE.md §1, §6).
"""
from fastapi import FastAPI, BackgroundTasks, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict
import os
import uuid
import base64
import shutil
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import config
import providers
import observability as obs

app = FastAPI(title="PhotoDukaan API")

# CORS: comma-separated ALLOWED_ORIGINS, or "*" for hackathon. Credentials off
# because the frontend never sends cookies (and "*" + credentials is invalid).
# Harden against footguns: an empty value falls back to "*" (an empty allow-list
# would silently block ALL cross-origin requests), and trailing slashes are
# stripped so "https://app.vercel.app/" still matches the Origin header (which
# never has a trailing slash).
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*").strip()
_origins = [o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()]
if not _origins or "*" in _origins:
    _origins = ["*"]
_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX") or None  # e.g. Vercel preview URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
print(f"[main] CORS allow_origins={_origins} regex={_origin_regex}")

os.makedirs(config.STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# --- In-memory store (mirrors the Supabase schema) ------------------------
sessions_db: Dict[str, dict] = {}
assets_db: Dict[str, dict] = {}

# Fields that must NEVER leave the backend (huge / internal).
_PRIVATE_SESSION_FIELDS = ("product_b64", "mime_type")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_session(session: dict) -> dict:
    return {k: v for k, v in session.items() if k not in _PRIVATE_SESSION_FIELDS}


# --- Pydantic models ------------------------------------------------------
class EditRequest(BaseModel):
    session_id: str
    instruction: str
    base_asset_id: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str  # "approved" | "rejected"


class AnimateRequest(BaseModel):
    session_id: str
    asset_id: str


# --- Background tasks ------------------------------------------------------
async def mirror_session(session_id: str):
    session = sessions_db.get(session_id)
    if session:
        await providers.db_upsert_session(session)


async def mirror_asset(asset_id: str):
    asset = assets_db.get(asset_id)
    if asset:
        await providers.db_upsert_asset(asset)


async def process_reel_background(session_id: str):
    """Generate the reel from the current seed asset. Never raises."""
    session = sessions_db.get(session_id)
    if not session:
        return
    try:
        session["reel_status"] = "rendering"
        seed_id = session.get("reel_seed_asset_id")
        hero = assets_db.get(seed_id) if seed_id else None
        hero_url = hero["url"] if hero else session.get("product_image_url")

        reel_url = await providers.generate_reel(session, hero_url)
        session["reel_url"] = reel_url
        session["reel_status"] = "ready"
    except Exception as e:
        print(f"[main] reel generation failed: {e}")
        session["reel_status"] = "failed"
    await providers.db_upsert_session(session)


async def sync_asset_background(session_id: str, asset_id: str, is_approved: bool):
    """Push an asset to Drive (Drafts or Approved). Never surfaces to the UI."""
    folder = "Approved" if is_approved else "Drafts"
    session = sessions_db.get(session_id)
    asset = assets_db.get(asset_id)
    if not session or not asset:
        return
    try:
        asset["drive_status"] = "syncing"
        file_id, status = await providers.sync_asset_to_drive(session, folder, asset)
        asset["drive_file_id"] = file_id
        asset["drive_url"] = providers.drive_url_for(file_id)
        asset["drive_status"] = status
    except Exception as e:
        print(f"[main] drive sync failed: {e}")
        asset["drive_status"] = "failed"
    await providers.db_upsert_asset(asset)


# --- Endpoints ------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": config.MOCK_MODE,
        "demo_fallback": config.DEMO_FALLBACK,
        "supabase": providers.db_available(),
        "langfuse": config.LANGFUSE_ENABLED,
    }


@app.post("/api/session")
async def create_session(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Create a session from an uploaded photo."""
    session_id = str(uuid.uuid4())
    file_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"
    b64_string = base64.b64encode(file_bytes).decode("utf-8")

    product_name = await providers.identify_product(b64_string, mime_type)

    # Per-product folders; de-dupe if the same product name recurs in-session.
    base_name = product_name
    product_folder = base_name
    counter = 1
    while os.path.exists(os.path.join(config.STATIC_DIR, "assets", session_id, "draft", product_folder)):
        product_folder = f"{base_name}-{counter}"
        counter += 1

    draft_dir = os.path.join(config.STATIC_DIR, "assets", session_id, "draft", product_folder)
    approved_dir = os.path.join(config.STATIC_DIR, "assets", session_id, "approved", product_folder)
    os.makedirs(draft_dir, exist_ok=True)
    os.makedirs(approved_dir, exist_ok=True)

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    file_path = os.path.join(draft_dir, f"{session_id}_original.{ext}")
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    url_tail = os.path.relpath(file_path, config.STATIC_DIR).replace("\\", "/")
    product_image_url = f"{config.PUBLIC_BASE_URL}/static/{url_tail}"

    sessions_db[session_id] = {
        "id": session_id,
        "product_image_url": product_image_url,
        "product_b64": b64_string,
        "mime_type": mime_type,
        "product_name": product_name,
        "product_folder": product_folder,
        "chain_interaction_id": None,
        "reel_status": "pending",
        "reel_url": None,
        "reel_seed_asset_id": None,
        "created_at": _now(),
    }
    background_tasks.add_task(mirror_session, session_id)

    return {"session_id": session_id, "product_name": product_name, "product_folder": product_folder}


@app.post("/api/generate-angles")
async def generate_angles(background_tasks: BackgroundTasks, session_id: str = Form(...)):
    """Generate 4 catalog angles; enqueue reel + Drive sync."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")

    angles = await providers.generate_angles(sessions_db[session_id])

    created = []
    for angle in angles:
        asset_id = str(uuid.uuid4())
        asset = {
            "id": asset_id, "session_id": session_id, "status": "draft",
            "drive_status": "pending", "drive_file_id": None, "created_at": _now(),
            **angle,
        }
        assets_db[asset_id] = asset
        created.append(asset)
        background_tasks.add_task(mirror_asset, asset_id)
        # Drive sync is now deferred until approval

    return {"assets": created}


@app.post("/api/edit")
async def edit_image(req: EditRequest, background_tasks: BackgroundTasks):
    """Conversational edit. On failure returns a friendly message, never a 500."""
    if req.session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await providers.edit_image(sessions_db[req.session_id], req.instruction, req.base_asset_id)

    if not result.get("ok", True):
        # Degradation path: no asset, polite chat message for the seller.
        return {"asset": None, "message": result.get("message", providers.STUDIO_HICCUP)}

    if result.get("chain_interaction_id"):
        sessions_db[req.session_id]["chain_interaction_id"] = result["chain_interaction_id"]
        background_tasks.add_task(mirror_session, req.session_id)

    asset_id = str(uuid.uuid4())
    asset = {
        "id": asset_id, "session_id": req.session_id, "status": "draft",
        "drive_status": "pending", "drive_file_id": None, "created_at": _now(),
        **{k: v for k, v in result.items() if k not in ("ok", "chain_interaction_id")},
    }
    assets_db[asset_id] = asset
    background_tasks.add_task(mirror_asset, asset_id)
    # Drive sync is now deferred until approval

    return {"asset": asset, "message": None}


@app.post("/api/assets/{asset_id}/status")
async def update_asset_status(asset_id: str, req: StatusUpdate, background_tasks: BackgroundTasks):
    """Approve or reject an asset."""
    if asset_id not in assets_db:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = assets_db[asset_id]
    asset["status"] = req.status
    reanimate_hint = False

    if req.status == "approved":
        session_id = asset["session_id"]
        session = sessions_db.get(session_id, {})

        # Copy the file into the approved/ folder locally.
        try:
            src = providers._url_to_local_path(asset["url"])
            approved_dir = os.path.join(config.STATIC_DIR, "assets", session_id, "approved",
                                        session.get("product_folder", "Product"))
            os.makedirs(approved_dir, exist_ok=True)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(approved_dir, os.path.basename(src)))
        except Exception as e:
            print(f"[main] approved copy failed: {e}")

        # Drive sync ONLY on approval
        background_tasks.add_task(sync_asset_background, session_id, asset_id, True)

        # Offer "Animate this shot?" when any asset is approved, instead of automatically triggering
        if asset.get("kind") in ("angle", "edit"):
            reanimate_hint = True

    background_tasks.add_task(mirror_asset, asset_id)
    return {**asset, "reanimate_hint": reanimate_hint}


@app.post("/api/animate")
async def request_animation(req: AnimateRequest, background_tasks: BackgroundTasks):
    """Re-animate the reel from a chosen asset."""
    if req.session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.asset_id not in assets_db:
        raise HTTPException(status_code=404, detail="Asset not found")

    sessions_db[req.session_id]["reel_seed_asset_id"] = req.asset_id
    background_tasks.add_task(process_reel_background, req.session_id)
    return {"status": "rendering started"}


@app.post("/api/session/{session_id}/approve_reel")
async def approve_reel(session_id: str, background_tasks: BackgroundTasks):
    """Approve the generated reel so it shows up in the store."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions_db[session_id]
    if session.get("reel_status") == "ready":
        session["reel_status"] = "approved"
        background_tasks.add_task(mirror_session, session_id)
        
    return {"status": session["reel_status"]}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Full session state (chat screen polls this). Base64 stripped."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    session_assets = [a for a in assets_db.values() if a["session_id"] == session_id]
    return {"session": _public_session(sessions_db[session_id]), "assets": session_assets}


@app.get("/api/store")
async def get_global_store():
    """All approved assets across all sessions for the global storefront."""
    store_items = []
    
    # Group by session (which represents a product upload)
    for session_id, session in sessions_db.items():
        approved = [a for a in assets_db.values()
                    if a.get("session_id") == session_id and a.get("status") == "approved"]
        
        if len(approved) > 0:
            store_items.append({
                "session_id": session_id,
                "product_name": session.get("product_name") or "Product",
                "product_folder": session.get("product_folder") or "Product",
                "reel_url": session.get("reel_url") if session.get("reel_status") == "approved" else None,
                "reel_status": session.get("reel_status") or "pending",
                "assets": approved,
                "created_at": session.get("created_at") or ""
            })
            
    # Sort newest first
    store_items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": store_items}


@app.get("/api/store/{session_id}")
async def get_store(session_id: str):
    """Approved assets + reel for the storefront (polled every 3s)."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions_db[session_id]
    approved = [a for a in assets_db.values()
                if a["session_id"] == session_id and a["status"] == "approved"]
    return {
        "product_name": session.get("product_name") or "Product",
        "reel_url": session.get("reel_url") if session.get("reel_status") == "approved" else None,
        "reel_status": session.get("reel_status"),
        "assets": approved,
    }


@app.get("/api/admin/{session_id}")
async def get_admin(session_id: str):
    """All assets with model/latency/cost/drive fields for the review board."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    session_assets = [a for a in assets_db.values() if a["session_id"] == session_id]
    total_cost = sum(a.get("cost_usd", 0) or 0 for a in session_assets)
    return {
        "session": _public_session(sessions_db[session_id]),
        "assets": session_assets,
        "total_cost": total_cost,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
