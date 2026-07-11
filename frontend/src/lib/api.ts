export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface Asset {
  id: string;
  session_id: string;
  kind: "angle" | "edit" | "reel";
  label: string;
  status: "draft" | "approved" | "rejected";
  url: string;
  model: string;
  latency_ms: number;
  cost_usd: number;
  drive_file_id?: string | null;
  drive_url?: string | null;
  drive_status: "pending" | "synced" | "skipped" | "failed" | "syncing";
  prompt?: string;
  created_at: string;
}

export interface Session {
  id: string;
  product_image_url: string;
  product_name?: string;
  product_folder?: string;
  chain_interaction_id?: string | null;
  reel_status: "pending" | "rendering" | "ready" | "approved" | "failed";
  reel_url?: string | null;
  reel_seed_asset_id?: string | null;
  created_at: string;
}

export const api = {
  // Create a new session
  createSession: async (file?: File): Promise<{ session_id: string, product_name?: string, product_folder?: string }> => {
    const formData = new FormData();
    if (file) {
      formData.append("file", file);
    } else {
      // For mock mode without a real file upload, we can just send a dummy file
      const blob = new Blob(["dummy content"], { type: "image/jpeg" });
      formData.append("file", blob, "dummy.jpg");
    }

    const res = await fetch(`${API_BASE}/api/session`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Failed to create session");
    return res.json();
  },

  // Generate initial angles
  generateAngles: async (sessionId: string): Promise<{ assets: Asset[] }> => {
    const formData = new FormData();
    formData.append("session_id", sessionId);

    const res = await fetch(`${API_BASE}/api/generate-angles`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Failed to generate angles");
    return res.json();
  },

  // Send an edit instruction
  editImage: async (
    sessionId: string,
    instruction: string,
    baseAssetId?: string
  ): Promise<{ asset: Asset | null; message: string | null }> => {
    const res = await fetch(`${API_BASE}/api/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        instruction,
        base_asset_id: baseAssetId,
      }),
    });
    if (!res.ok) throw new Error("Failed to edit image");
    return res.json();
  },

  // Update asset status (approve/reject)
  updateAssetStatus: async (
    assetId: string,
    status: "approved" | "rejected"
  ): Promise<Asset & { reanimate_hint?: boolean }> => {
    const res = await fetch(`${API_BASE}/api/assets/${assetId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error("Failed to update status");
    return res.json();
  },

  // Trigger re-animation
  animate: async (
    sessionId: string,
    assetId: string
  ): Promise<{ status: string }> => {
    const res = await fetch(`${API_BASE}/api/animate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, asset_id: assetId }),
    });
    if (!res.ok) throw new Error("Failed to start animation");
    return res.json();
  },

  approveReel: async (
    sessionId: string
  ): Promise<{ status: string }> => {
    const res = await fetch(`${API_BASE}/api/session/${sessionId}/approve_reel`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to approve reel");
    return res.json();
  },

  // Polling endpoints
  getSession: async (
    sessionId: string
  ): Promise<{ session: Session; assets: Asset[] }> => {
    const res = await fetch(`${API_BASE}/api/session/${sessionId}`);
    if (!res.ok) throw new Error("Failed to fetch session");
    return res.json();
  },

  getAllStore: async (): Promise<{ items: { session_id: string, product_name: string, product_folder: string, reel_url: string | null, reel_status: string, assets: Asset[], created_at: string }[] }> => {
    const res = await fetch(`${API_BASE}/api/store`);
    if (!res.ok) throw new Error("Failed to fetch global store");
    return res.json();
  },

  getStore: async (
    sessionId: string
  ): Promise<{ product_name: string; reel_url: string | null; reel_status: string; assets: Asset[] }> => {
    const res = await fetch(`${API_BASE}/api/store/${sessionId}`);
    if (!res.ok) throw new Error("Failed to fetch store");
    return res.json();
  },
};
