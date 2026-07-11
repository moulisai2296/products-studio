-- PhotoDukaan Supabase schema (CLAUDE.md section 6). Exactly 2 tables. No RLS, no auth.
-- Backend uses the service key. Safe to run repeatedly (idempotent).

create table if not exists sessions (
  id                    text primary key,
  product_image_url     text,
  product_name          text,
  product_folder        text,
  chain_interaction_id  text,
  reel_status           text default 'pending',   -- pending|rendering|ready|failed
  reel_url              text,
  reel_seed_asset_id    text,
  created_at            timestamptz default now()
);

create table if not exists assets (
  id            text primary key,
  session_id    text references sessions(id),
  kind          text,                              -- angle|edit|reel
  label         text,
  status        text default 'draft',              -- draft|approved|rejected
  url           text,
  model         text,
  latency_ms    int,
  cost_usd      numeric,
  drive_file_id text,
  drive_url     text,                              -- clickable Drive link (built from file id)
  drive_status  text default 'pending',            -- pending|synced|skipped|syncing|failed
  prompt        text,
  created_at    timestamptz default now()
);

create index if not exists idx_assets_session on assets(session_id);
create index if not exists idx_assets_status  on assets(status);

-- Self-healing: add columns that go beyond the base spec if an older schema
-- was created first (create-table-if-not-exists won't add columns to an
-- existing table). Safe to run repeatedly.
alter table sessions add column if not exists product_name   text;
alter table sessions add column if not exists product_folder text;
alter table assets   add column if not exists drive_url      text;
