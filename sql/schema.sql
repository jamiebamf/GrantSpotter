create extension if not exists pgcrypto;

create table if not exists public.grant_sources (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  source_name text not null,
  base_url text not null,
  grants_page_url text not null,
  source_type text not null default 'official',
  crawl_frequency text not null default 'daily',
  trust_score integer not null default 100 check (trust_score between 0 and 100),
  robots_allowed boolean not null default true,
  is_active boolean not null default true,
  last_crawled_at timestamptz,
  last_crawl_success boolean,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.crawl_pages (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.grant_sources(id) on delete cascade,
  url text unique not null,
  page_title text,
  raw_html text,
  clean_text text,
  http_status integer,
  content_hash text,
  processing_status text not null default 'new',
  error_message text,
  first_discovered_at timestamptz not null default now(),
  last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.grants (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.grant_sources(id),
  source_page_id uuid references public.crawl_pages(id),
  fingerprint text unique not null,
  grant_title text not null,
  funder_name text not null,
  summary text not null default '',
  minimum_amount numeric(14,2),
  maximum_amount numeric(14,2),
  opening_date date,
  deadline date,
  deadline_type text not null default 'unknown' check (deadline_type in ('fixed','rolling','unknown')),
  application_url text,
  official_source_url text not null,
  eligible_regions jsonb not null default '[]'::jsonb,
  eligible_causes jsonb not null default '[]'::jsonb,
  eligible_organisation_types jsonb not null default '[]'::jsonb,
  turnover_requirements text not null default '',
  charity_registration_required boolean,
  match_funding_required boolean,
  application_process text not null default '',
  is_currently_open boolean,
  evidence jsonb not null default '{}'::jsonb,
  confidence_score integer not null default 0 check (confidence_score between 0 and 100),
  verification_status text not null default 'review' check (verification_status in ('draft','review','approved','published','closed','rejected')),
  validation_notes jsonb not null default '[]'::jsonb,
  content_hash text,
  first_seen_at timestamptz not null default now(),
  last_verified_at timestamptz,
  reviewed_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists grants_status_idx on public.grants(verification_status);
create index if not exists grants_deadline_idx on public.grants(deadline);
create index if not exists grants_funder_idx on public.grants(funder_name);
create index if not exists grants_regions_gin_idx on public.grants using gin(eligible_regions);
create index if not exists grants_causes_gin_idx on public.grants using gin(eligible_causes);

create table if not exists public.grant_reviews (
  id uuid primary key default gen_random_uuid(),
  grant_id uuid not null references public.grants(id) on delete cascade,
  reason text not null,
  original_extraction jsonb not null default '{}'::jsonb,
  suggested_data jsonb,
  review_status text not null default 'pending' check (review_status in ('pending','approved','rejected','merged')),
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);

insert into public.grant_sources (slug, source_name, base_url, grants_page_url, source_type, trust_score)
values
  ('govuk-find-a-grant', 'GOV.UK Find a Grant', 'https://www.find-government-grants.service.gov.uk', 'https://www.find-government-grants.service.gov.uk/grants', 'official-government', 100),
  ('ukri-opportunities', 'UKRI Funding Opportunities', 'https://www.ukri.org', 'https://www.ukri.org/opportunity/', 'official-public-body', 100),
  ('govuk-business-finance', 'GOV.UK Business Finance Support', 'https://www.gov.uk', 'https://www.gov.uk/business-finance-support?types_of_support%5B%5D=grant', 'official-government', 100),
  ('fcdo-development-funding', 'FCDO International Development Funding', 'https://www.gov.uk', 'https://www.gov.uk/international-development-funding', 'official-government', 100),
  ('scotland-business-funding', 'Find Business Support Scotland', 'https://findbusinesssupport.gov.scot', 'https://findbusinesssupport.gov.scot/search?type=Funding', 'official-government', 100),
  ('national-lottery-community-fund', 'The National Lottery Community Fund', 'https://www.tnlcommunityfund.org.uk', 'https://www.tnlcommunityfund.org.uk/funding/programmes', 'official-funder', 98),
  ('heritage-fund', 'National Lottery Heritage Fund', 'https://www.heritagefund.org.uk', 'https://www.heritagefund.org.uk/funding', 'official-funder', 98),
  ('arts-council-england', 'Arts Council England', 'https://www.artscouncil.org.uk', 'https://www.artscouncil.org.uk/our-open-funds', 'official-public-body', 98),
  ('sport-england-funds', 'Sport England Funds', 'https://www.sportengland.org', 'https://www.sportengland.org/funds-and-campaigns/our-funds', 'official-public-body', 98)
on conflict (slug) do update set
  source_name = excluded.source_name,
  base_url = excluded.base_url,
  grants_page_url = excluded.grants_page_url,
  source_type = excluded.source_type,
  trust_score = excluded.trust_score,
  is_active = true,
  updated_at = now();

alter table public.grant_sources enable row level security;
alter table public.crawl_pages enable row level security;
alter table public.grants enable row level security;
alter table public.grant_reviews enable row level security;

-- The crawler uses the Supabase service-role key, which bypasses RLS.
-- Do not expose the service-role key in the PHP website or browser.
