import os
import time
import asyncio
import uuid
import base64
import json
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

MOCK_MODE = os.getenv("MOCK_MODE", "1") == "1"

try:
    gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
except Exception as e:
    print(f"Warning: Could not init genai client: {e}")
    gemini_client = None

# In mock mode, we simulate latencies to feel realistic
LATENCY_LITE = 3.8
LATENCY_NB2 = 6.2
LATENCY_REEL = 35.0
LATENCY_DIRECTOR = 1.2

class MockGeminiClient:
    """Mock implementation for Gemini models"""
    
    @staticmethod
    async def identify_product(b64_string: str, mime_type: str) -> str:
        await asyncio.sleep(0.5)
        return "Saree"

    @staticmethod
    async def generate_angles(session: dict):
        await asyncio.sleep(LATENCY_LITE)
        base_url = "http://localhost:8000/static/seed"
        angles = [
            {"kind": "angle", "label": "Front Drape", "url": f"{base_url}/angle_front.png", "model": "gemini-3.1-flash-lite-image", "latency_ms": int(LATENCY_LITE*1000), "cost_usd": 0.034},
            {"kind": "angle", "label": "Three-Quarter", "url": f"{base_url}/angle_34.png", "model": "gemini-3.1-flash-lite-image", "latency_ms": int(LATENCY_LITE*1000), "cost_usd": 0.034},
            {"kind": "angle", "label": "Detail Close-up", "url": f"{base_url}/angle_detail.png", "model": "gemini-3.1-flash-lite-image", "latency_ms": int(LATENCY_LITE*1000), "cost_usd": 0.034},
            {"kind": "angle", "label": "Flat Lay", "url": f"{base_url}/angle_flat.png", "model": "gemini-3.1-flash-lite-image", "latency_ms": int(LATENCY_LITE*1000), "cost_usd": 0.034},
        ]
        return angles

    @staticmethod
    async def edit_image(session: dict, prompt: str, base_asset_id: str = None):
        await asyncio.sleep(LATENCY_DIRECTOR + LATENCY_NB2)
        base_url = "http://localhost:8000/static/seed"
        
        if "text" in prompt.lower() or "offer" in prompt.lower() or "दिवाली" in prompt:
            url = f"{base_url}/edit_festive_text.png"
            label = "Festive Offer"
        else:
            url = f"{base_url}/edit_model_wedding.png"
            label = "Model at Wedding"
            
        return {
            "kind": "edit",
            "label": label,
            "url": url,
            "model": "gemini-3.1-flash-image",
            "latency_ms": int((LATENCY_DIRECTOR + LATENCY_NB2)*1000),
            "cost_usd": 0.067,
            "prompt": f"[Optimized] {prompt}",
            "chain_interaction_id": "mock_chain_id_123"
        }

    @staticmethod
    async def generate_reel():
        await asyncio.sleep(LATENCY_REEL)
        base_url = "http://localhost:8000/static/seed"
        return f"{base_url}/small_video.mp4"

class RealGeminiClient:
    """Real implementation using Gemini Interactions API"""
    
    @staticmethod
    def _identify_product_sync(b64_string: str, mime_type: str) -> str:
        try:
            image_part = {"inline_data": {"data": b64_string, "mime_type": mime_type}}
            res = gemini_client.models.generate_content(
                model='gemini-3.5-flash',
                contents=[image_part, "Identify the main product in this image in 1-2 words (e.g. Saree, Handbag, Watch, Shoes). Output only the product name, capitalized."],
            )
            return res.text.strip()
        except Exception as e:
            print(f"Product identification failed: {e}")
            return "Product"

    @staticmethod
    async def identify_product(b64_string: str, mime_type: str) -> str:
        if not gemini_client:
            raise Exception("Gemini client not initialized")
        return await asyncio.to_thread(RealGeminiClient._identify_product_sync, b64_string, mime_type)

    @staticmethod
    def _generate_single_angle_sync(session: dict, label: str, prompt_template: str):
        start_time = time.time()
        b64_string = session.get("product_b64")
        mime_type = session.get("mime_type", "image/jpeg")
        product_name = session.get("product_name", "Product")
        
        prompt = prompt_template.replace("{product_name}", product_name)
        
        interaction = gemini_client.interactions.create(
            model="gemini-3.1-flash-lite-image",
            input=[
                {"type": "image", "data": b64_string, "mime_type": mime_type},
                {"type": "text", "text": prompt},
            ],
            response_format={"type": "image", "aspect_ratio": "4:5", "image_size": "1K"},
        )
        
        image_b64 = interaction.output_image.data
        image_bytes = base64.b64decode(image_b64)
        
        filename = f"{session['id']}_angle_{uuid.uuid4().hex[:8]}.jpeg"
        # Save to the specific draft folder
        draft_dir = os.path.join("static", "assets", session['id'], "draft", session.get('product_folder', 'Product'))
        os.makedirs(draft_dir, exist_ok=True)
        file_path = os.path.join(draft_dir, filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
            
        latency = time.time() - start_time
        
        url_path = file_path.replace("\\", "/").replace("static/", "")
        
        return {
            "kind": "angle",
            "label": label,
            "url": f"http://localhost:8000/static/{url_path}",
            "model": "gemini-3.1-flash-lite-image",
            "latency_ms": int(latency * 1000),
            "cost_usd": 0.034
        }
        
    @staticmethod
    async def generate_angles(session: dict):
        if not gemini_client:
            raise Exception("Gemini client not initialized")
            
        angle_prompts = [
            {"label": "Front Drape", "prompt": "Professional catalog photo of a {product_name}, front view, full shot, clean background"},
            {"label": "Three-Quarter", "prompt": "Professional catalog photo of a {product_name}, three-quarter angle, clean background"},
            {"label": "Detail Close-up", "prompt": "Professional catalog photo of a {product_name}, extreme close-up on detail and texture, clean background"},
            {"label": "Flat Lay", "prompt": "Professional catalog photo of a {product_name}, flat lay from directly above, neat folding, clean background"},
        ]
        
        # Run sequentially to avoid rate limiting for now, can be parallelized later
        angles = []
        for ap in angle_prompts:
            try:
                angle = await asyncio.to_thread(RealGeminiClient._generate_single_angle_sync, session, ap["label"], ap["prompt"])
                angles.append(angle)
            except Exception as e:
                print(f"Failed to generate angle {ap['label']}: {e}")
                
        return angles

    @staticmethod
    def _edit_image_sync(session: dict, instruction: str):
        start_time = time.time()
        
        # Director step
        director_prompt = f"""
You are a professional e-commerce photoshoot director.
The seller has provided this instruction: "{instruction}"
Convert this into ONE optimized English image-editing prompt.
Hard rules:
(a) never alter the product's colors/patterns/textures.
(b) if on-image text is requested, state the exact text in double quotes FIRST, then instruct accurate rendering in that script.
(c) keep it professional e-commerce photography style.
Output ONLY the optimized prompt, no conversational filler.
"""
        try:
            director_res = gemini_client.models.generate_content(
                model='gemini-3.5-flash',
                contents=director_prompt,
            )
            optimized_prompt = director_res.text.strip()
        except Exception as e:
            print(f"Director failed: {e}")
            optimized_prompt = instruction
            
        # Edit step
        chain_id = session.get("chain_interaction_id")
        
        if chain_id:
            interaction = gemini_client.interactions.create(
                model="gemini-3.1-flash-image",
                input=[{"type": "text", "text": optimized_prompt}],
                previous_interaction_id=chain_id,
                response_format={"type": "image", "aspect_ratio": "4:5"},
            )
        else:
            b64_string = session.get("product_b64")
            mime_type = session.get("mime_type", "image/jpeg")
            interaction = gemini_client.interactions.create(
                model="gemini-3.1-flash-image",
                input=[
                    {"type": "image", "data": b64_string, "mime_type": mime_type},
                    {"type": "text", "text": optimized_prompt},
                ],
                response_format={"type": "image", "aspect_ratio": "4:5"},
            )
            
        image_b64 = interaction.output_image.data
        image_bytes = base64.b64decode(image_b64)
        new_chain_id = interaction.id
        
        filename = f"{session['id']}_edit_{uuid.uuid4().hex[:8]}.jpeg"
        draft_dir = os.path.join("static", "assets", session['id'], "draft", session.get('product_folder', 'Product'))
        os.makedirs(draft_dir, exist_ok=True)
        file_path = os.path.join(draft_dir, filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
            
        latency = time.time() - start_time
        url_path = file_path.replace("\\", "/").replace("static/", "")
        
        label = "Custom Edit"
        if "wedding" in instruction.lower(): label = "Model at Wedding"
        elif "दिवाली" in instruction or "offer" in instruction.lower(): label = "Festive Offer"
        
        return {
            "kind": "edit",
            "label": label,
            "url": f"http://localhost:8000/static/assets/{filename}",
            "model": "gemini-3.1-flash-image",
            "latency_ms": int(latency * 1000),
            "cost_usd": 0.067,
            "prompt": f"[Optimized] {optimized_prompt}",
            "chain_interaction_id": new_chain_id
        }

    @staticmethod
    async def edit_image(session: dict, instruction: str, base_asset_id: str = None):
        if not gemini_client:
            raise Exception("Gemini client not initialized")
        return await asyncio.to_thread(RealGeminiClient._edit_image_sync, session, instruction)

class MockDriveClient:
    """Mock implementation for Google Drive sync"""
    @staticmethod
    async def sync_asset(session: dict, folder_type: str, asset: dict):
        await asyncio.sleep(1.5)
        return "mock_drive_file_id_456", "synced"

class RealDriveClient:
    """Real implementation for Google Drive sync"""
    
    @staticmethod
    def _sync_asset_sync(session: dict, folder_type: str, asset: dict):
        drive_parent_folder_id = os.getenv("DRIVE_PARENT_FOLDER_ID")
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        
        if not drive_parent_folder_id or not service_account_json:
            print("Drive credentials missing. Skipping sync.")
            return None, "skipped"
            
        try:
            creds_info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_info, scopes=['https://www.googleapis.com/auth/drive.file']
            )
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # 1. Create or get Session folder
            session_folder_name = session['id']
            query = f"name='{session_folder_name}' and '{drive_parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if not items:
                file_metadata = {
                    'name': session_folder_name,
                    'parents': [drive_parent_folder_id],
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                session_folder = drive_service.files().create(body=file_metadata, fields='id').execute()
                session_folder_id = session_folder.get('id')
            else:
                session_folder_id = items[0].get('id')
                
            # 2. Create or get Subfolder (Drafts or Approved)
            query = f"name='{folder_type}' and '{session_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if not items:
                file_metadata = {
                    'name': folder_type,
                    'parents': [session_folder_id],
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                subfolder = drive_service.files().create(body=file_metadata, fields='id').execute()
                subfolder_id = subfolder.get('id')
            else:
                subfolder_id = items[0].get('id')
                
            # 3. Create or get Product Folder
            product_folder_name = session.get('product_folder', 'Product')
            query = f"name='{product_folder_name}' and '{subfolder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if not items:
                file_metadata = {
                    'name': product_folder_name,
                    'parents': [subfolder_id],
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                product_folder = drive_service.files().create(body=file_metadata, fields='id').execute()
                product_folder_id = product_folder.get('id')
            else:
                product_folder_id = items[0].get('id')
                
            # 4. Upload File
            url_path = asset["url"].split("/static/")[-1]
            local_file_path = os.path.join("static", url_path)
            
            if not os.path.exists(local_file_path):
                print(f"File {local_file_path} not found.")
                return None, "failed"
                
            file_name = os.path.basename(local_file_path)
            file_metadata = {
                'name': file_name,
                'parents': [product_folder_id]
            }
            media = MediaFileUpload(local_file_path, resumable=True)
            
            uploaded_file = drive_service.files().create(
                body=file_metadata, media_body=media, fields='id'
            ).execute()
            
            return uploaded_file.get('id'), "synced"
            
        except Exception as e:
            print(f"Drive upload failed: {e}")
            return None, "failed"
            
    @staticmethod
    async def sync_asset(session: dict, folder_type: str, asset: dict):
        return await asyncio.to_thread(RealDriveClient._sync_asset_sync, session, folder_type, asset)


async def identify_product(b64_string: str, mime_type: str) -> str:
    if MOCK_MODE:
        return "Saree" # Mock return
    return await RealGeminiClient.identify_product(b64_string, mime_type)

async def generate_angles(session: dict):
    if MOCK_MODE:
        return await MockGeminiClient.generate_angles(session)
    return await RealGeminiClient.generate_angles(session)

async def edit_image(session: dict, prompt: str, base_asset_id: str = None):
    if MOCK_MODE:
        return await MockGeminiClient.edit_image(session, prompt, base_asset_id)
    return await RealGeminiClient.edit_image(session, prompt, base_asset_id)

async def generate_reel():
    # Omni Flash is not wired up yet, fallback to mock
    return await MockGeminiClient.generate_reel()

async def sync_asset_to_drive(session: dict, folder_type: str, asset: dict):
    if MOCK_MODE:
        return await MockDriveClient.sync_asset(session, folder_type, asset)
    return await RealDriveClient.sync_asset(session, folder_type, asset)
