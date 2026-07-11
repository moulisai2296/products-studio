from fastapi import FastAPI, BackgroundTasks, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
import time
import os
import base64
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import providers

app = FastAPI(title="PhotoDukaan API")

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For hackathon, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (where we put our seed images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- In-Memory Store (Mocking Supabase) ---
# sessions = { "id": { ... } }
sessions_db: Dict[str, dict] = {}
# assets = { "id": { ... } }
assets_db: Dict[str, dict] = {}

# --- Pydantic Models ---
class EditRequest(BaseModel):
    session_id: str
    instruction: str
    base_asset_id: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str # "approved" or "rejected"

class AnimateRequest(BaseModel):
    session_id: str
    asset_id: str

# --- Background Tasks ---
async def process_reel_background(session_id: str):
    """Background task to generate video reel"""
    try:
        sessions_db[session_id]["reel_status"] = "rendering"
        # Simulate video generation
        video_url = await providers.generate_reel()
        
        sessions_db[session_id]["reel_url"] = video_url
        sessions_db[session_id]["reel_status"] = "ready"
    except Exception as e:
        print(f"Reel generation failed: {e}")
        sessions_db[session_id]["reel_status"] = "failed"

async def sync_asset_background(session_id: str, asset_id: str, is_approved: bool):
    """Background task to sync asset to Google Drive"""
    folder = "Approved" if is_approved else "Drafts"
    try:
        assets_db[asset_id]["drive_status"] = "syncing"
        session = sessions_db[session_id]
        asset = assets_db[asset_id]
        drive_file_id, status = await providers.sync_asset_to_drive(session, folder, asset)
        assets_db[asset_id]["drive_file_id"] = drive_file_id
        assets_db[asset_id]["drive_status"] = status
    except Exception as e:
        print(f"Drive sync failed: {e}")
        assets_db[asset_id]["drive_status"] = "failed"


# --- Endpoints ---

@app.post("/api/session")
async def create_session(file: UploadFile = File(...)):
    """Creates a new session from an uploaded photo"""
    session_id = str(uuid.uuid4())
    
    file_bytes = await file.read()
    
    # Store base64 representation for Gemini inputs
    mime_type = file.content_type or "image/jpeg"
    b64_string = base64.b64encode(file_bytes).decode('utf-8')
    
    # Identify product dynamically
    product_name = await providers.identify_product(b64_string, mime_type)
    
    # Handle duplicate product names
    base_product_name = product_name
    counter = 1
    # Check if a product with the same name exists across all sessions or just this session?
    # The requirement says "if duplicate products found put it as product-1, product-2 like that inside drafts and approved folders"
    # Usually this means if multiple products are uploaded. Currently a session handles one product.
    # To be safe globally or if we reuse sessions:
    product_folder = base_product_name
    while os.path.exists(os.path.join("static", "assets", session_id, "draft", product_folder)):
        product_folder = f"{base_product_name}-{counter}"
        counter += 1
        
    draft_dir = os.path.join("static", "assets", session_id, "draft", product_folder)
    approved_dir = os.path.join("static", "assets", session_id, "approved", product_folder)
    os.makedirs(draft_dir, exist_ok=True)
    os.makedirs(approved_dir, exist_ok=True)
    
    # Save uploaded file
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    filename = f"{session_id}_original.{file_extension}"
    file_path = os.path.join(draft_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    url_path = file_path.replace("\\", "/").replace("static/", "")
    product_image_url = f"http://localhost:8000/static/{url_path}"
    
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
        "created_at": datetime.now().isoformat()
    }
    
    return {"session_id": session_id, "product_name": product_name, "product_folder": product_folder}

@app.post("/api/generate-angles")
async def generate_angles(session_id: str = Form(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """Generates 4 catalog angles, kicks off background reel and drive sync"""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    angles = await providers.generate_angles(sessions_db[session_id])
    
    created_assets = []
    for angle in angles:
        asset_id = str(uuid.uuid4())
        asset = {
            "id": asset_id,
            "session_id": session_id,
            "status": "draft",
            "drive_status": "pending",
            "drive_file_id": None,
            "prompt": angle.get("label"),
            "created_at": datetime.now().isoformat(),
            **angle # merge url, label, kind, model, latency, cost
        }
        assets_db[asset_id] = asset
        created_assets.append(asset)
        
        # Enqueue drive sync for drafts
        background_tasks.add_task(sync_asset_background, session_id, asset_id, is_approved=False)
        
    # Start reel generation using the first angle as hero
    sessions_db[session_id]["reel_seed_asset_id"] = created_assets[0]["id"]
    background_tasks.add_task(process_reel_background, session_id)
    
    return {"assets": created_assets}

@app.post("/api/edit")
async def edit_image(req: EditRequest, background_tasks: BackgroundTasks):
    """Generates an edited image based on text instruction"""
    if req.session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    edit_result = await providers.edit_image(sessions_db[req.session_id], req.instruction, req.base_asset_id)
    
    asset_id = str(uuid.uuid4())
    asset = {
        "id": asset_id,
        "session_id": req.session_id,
        "status": "draft",
        "drive_status": "pending",
        "drive_file_id": None,
        "created_at": datetime.now().isoformat(),
        **edit_result
    }
    
    if edit_result.get("chain_interaction_id"):
        sessions_db[req.session_id]["chain_interaction_id"] = edit_result["chain_interaction_id"]
        
    assets_db[asset_id] = asset
    
    # Enqueue drive sync
    background_tasks.add_task(sync_asset_background, req.session_id, asset_id, is_approved=False)
    
    return {"asset": asset}

@app.post("/api/assets/{asset_id}/status")
async def update_asset_status(asset_id: str, req: StatusUpdate, background_tasks: BackgroundTasks):
    """Approves or rejects an asset"""
    if asset_id not in assets_db:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    assets_db[asset_id]["status"] = req.status
    
    if req.status == "approved":
        session_id = assets_db[asset_id]["session_id"]
        
        # Copy file locally to approved directory
        url_path = assets_db[asset_id]["url"].split("/static/")[-1]
        draft_file_path = os.path.join("static", url_path)
        
        product_folder = sessions_db[session_id].get("product_folder", "Product")
        approved_dir = os.path.join("static", "assets", session_id, "approved", product_folder)
        os.makedirs(approved_dir, exist_ok=True)
        
        filename = os.path.basename(draft_file_path)
        approved_file_path = os.path.join(approved_dir, filename)
        
        try:
            import shutil
            shutil.copy2(draft_file_path, approved_file_path)
        except Exception as e:
            print(f"Failed to copy {draft_file_path} to {approved_file_path}: {e}")
            
        background_tasks.add_task(sync_asset_background, session_id, asset_id, is_approved=True)
        
    return assets_db[asset_id]

@app.post("/api/animate")
async def request_animation(req: AnimateRequest, background_tasks: BackgroundTasks):
    """Re-animates the reel from a newly chosen asset"""
    if req.session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    sessions_db[req.session_id]["reel_seed_asset_id"] = req.asset_id
    background_tasks.add_task(process_reel_background, req.session_id)
    
    return {"status": "rendering started"}

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Returns full session state and all its assets"""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session_assets = [a for a in assets_db.values() if a["session_id"] == session_id]
    
    return {
        "session": sessions_db[session_id],
        "assets": session_assets
    }

@app.get("/api/store/{session_id}")
async def get_store(session_id: str):
    """Returns only approved assets and reel for the storefront"""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    approved_assets = [a for a in assets_db.values() if a["session_id"] == session_id and a["status"] == "approved"]
    
    return {
        "reel_url": sessions_db[session_id]["reel_url"] if sessions_db[session_id]["reel_status"] == "ready" else None,
        "assets": approved_assets
    }

@app.get("/api/admin/{session_id}")
async def get_admin(session_id: str):
    """Returns all assets with metrics for admin review board"""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session_assets = [a for a in assets_db.values() if a["session_id"] == session_id]
    
    total_cost = sum(a.get("cost_usd", 0) for a in session_assets)
    
    return {
        "session": sessions_db[session_id],
        "assets": session_assets,
        "total_cost": total_cost
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
