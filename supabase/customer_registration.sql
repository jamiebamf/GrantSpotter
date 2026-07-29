create extension if not exists pgcrypto;

create table if not exists public.customer_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  first_name text not null,
  last_name text not null,
  phone text,
  job_title text,
  marketing_consent boolean not null default false,
  terms_accepted_at timestamptz not null default now(),
  onboarding_status text not null default 'organisation_pending'
    check (onboarding_status in ('organisation_pending','profile_pending','complete','manual_review')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.customer_organisations (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  organisation_type text not null,
  legal_name text not null,
  trading_name text,
  company_number text,
  charity_number text,
  verification_source text,
  verification_status text not null default 'unverified'
    check (verification_status in ('unverified','register_found','customer_confirmed','manual_review','verified','failed')),
  verified_at timestamptz,
  official_data jsonb not null default '{}'::jsonb,
  registered_address jsonb not null default '{}'::jsonb,
  operating_address jsonb not null default '{}'::jsonb,
  website text,
  contact_phone text,
  description text,
  turnover_band text,
  employee_band text,
  geographic_areas text[] not null default '{}',
  causes text[] not null default '{}',
  beneficiaries text[] not null default '{}',
  preferred_grant_min numeric,
  preferred_grant_max numeric,
  match_funding_available boolean,
  previous_grant_experience text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists customer_organisations_company_number_unique
  on public.customer_organisations (upper(company_number))
  where company_number is not null;

create table if not exists public.customer_organisation_members (
  organisation_id uuid not null references public.customer_organisations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  member_role text not null default 'owner' check (member_role in ('owner','admin','member')),
  created_at timestamptz not null default now(),
  primary key (organisation_id, user_id)
);

alter table public.customer_profiles enable row level security;
alter table public.customer_organisations enable row level security;
alter table public.customer_organisation_members enable row level security;

create policy "Users can read own profile" on public.customer_profiles
  for select using (auth.uid() = user_id);
create policy "Users can update own profile" on public.customer_profiles
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "Members can read organisations" on public.customer_organisations
  for select using (
    exists (
      select 1 from public.customer_organisation_members m
      where m.organisation_id = id and m.user_id = auth.uid()
    )
  );
create policy "Owners can update organisations" on public.customer_organisations
  for update using (
    exists (
      select 1 from public.customer_organisation_members m
      where m.organisation_id = id and m.user_id = auth.uid() and m.member_role in ('owner','admin')
    )
  );

create policy "Users can read own memberships" on public.customer_organisation_members
  for select using (auth.uid() = user_id);
