create extension if not exists pgcrypto;

create table if not exists public.grant_fact_checks (
  id uuid primary key default gen_random_uuid(),
  grant_id uuid not null references public.grants(id) on delete cascade,
  status text not null default 'completed' check (status in ('running','completed','failed')),
  overall_verdict text not null check (overall_verdict in ('verified','needs_changes','insufficient_evidence')),
  overall_confidence integer not null default 0 check (overall_confidence between 0 and 100),
  summary text not null default '',
  source_url text not null,
  source_snapshot_hash text,
  raw_result jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists grant_fact_checks_grant_created_idx
  on public.grant_fact_checks(grant_id, created_at desc);

create table if not exists public.grant_field_checks (
  id uuid primary key default gen_random_uuid(),
  fact_check_id uuid not null references public.grant_fact_checks(id) on delete cascade,
  grant_id uuid not null references public.grants(id) on delete cascade,
  field_name text not null,
  current_value jsonb,
  suggested_value jsonb,
  verdict text not null check (verdict in ('confirmed','incorrect','missing','uncertain')),
  evidence text not null default '',
  evidence_url text not null,
  confidence integer not null default 0 check (confidence between 0 and 100),
  accepted boolean not null default false,
  accepted_at timestamptz,
  created_at timestamptz not null default now(),
  unique(fact_check_id, field_name)
);

create index if not exists grant_field_checks_fact_check_idx
  on public.grant_field_checks(fact_check_id);

create index if not exists grant_field_checks_grant_idx
  on public.grant_field_checks(grant_id);

grant all on table public.grant_fact_checks to service_role;
grant all on table public.grant_field_checks to service_role;
