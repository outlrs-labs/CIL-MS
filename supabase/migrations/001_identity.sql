-- Run once in Supabase SQL Editor, before scripts/bootstrap_admin.py.
begin;
create schema if not exists private;
revoke all on schema private from public;
create type public.entity_kind as enum ('holding','operating','technical');
create type public.app_role as enum ('cil_admin','subsidiary','cmpdi');
create table public.entities (
 id uuid primary key default gen_random_uuid(), code text not null unique check(code ~ '^[A-Z][A-Z0-9_]{1,15}$'),
 name text not null check(length(name) between 2 and 160), kind public.entity_kind not null,
 parent_id uuid references public.entities(id), location text not null default '', active boolean not null default true,
 created_at timestamptz not null default now(),
 check ((kind='holding' and parent_id is null) or (kind<>'holding' and parent_id is not null))
);
create unique index one_holding on public.entities(kind) where kind='holding';
create unique index one_technical on public.entities(kind) where kind='technical';
create table public.central_admin (
 singleton boolean primary key default true check(singleton), user_id uuid not null unique references auth.users(id) on delete restrict
);
create table public.profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 email text not null unique, full_name text not null check(length(full_name) between 2 and 100),
 role public.app_role not null, entity_id uuid not null references public.entities(id),
 active boolean not null default true, must_change_password boolean not null default true,
 created_at timestamptz not null default now()
);
create unique index one_cil_admin on public.profiles(role) where role='cil_admin';
create table public.access_events (
 id bigint generated always as identity primary key, actor_id uuid references auth.users(id),
 action text not null, target text not null, created_at timestamptz not null default now()
);
alter table public.entities enable row level security;
alter table public.profiles enable row level security;
alter table public.central_admin enable row level security;
alter table public.access_events enable row level security;
revoke all on public.entities, public.profiles, public.central_admin, public.access_events from anon, authenticated;
grant select on public.entities, public.profiles, public.access_events to authenticated;
grant all on public.entities, public.profiles, public.central_admin, public.access_events to service_role;
grant usage, select on sequence public.access_events_id_seq to service_role;

create function private.current_role() returns public.app_role language sql stable security definer set search_path='' as $$
 select p.role from public.profiles p join public.entities e on e.id=p.entity_id
 where p.id=(select auth.uid()) and p.active and e.active and not p.must_change_password
$$;
create function private.own_entity() returns uuid language sql stable security definer set search_path='' as $$
 select p.entity_id from public.profiles p where p.id=(select auth.uid()) and p.active
$$;
revoke all on function private.current_role(), private.own_entity() from public;
grant usage on schema private to authenticated;
grant execute on function private.current_role(), private.own_entity() to authenticated;
create policy profile_read on public.profiles for select to authenticated using(id=(select auth.uid()) or (select private.current_role())='cil_admin');
create policy entity_read on public.entities for select to authenticated using (
 (select private.current_role()) in ('cil_admin','cmpdi') or id=(select private.own_entity())
);
create policy event_read on public.access_events for select to authenticated using((select private.current_role())='cil_admin');
-- No authenticated INSERT/UPDATE/DELETE grants or policies, and no signup-to-profile trigger.

create function private.guard_profile() returns trigger language plpgsql set search_path='' as $$
declare k public.entity_kind; admin_id uuid;
begin
 if TG_OP='DELETE' then
  if old.role='cil_admin' then raise exception 'The singleton administrator cannot be deleted'; end if;
  return old;
 end if;
 if TG_OP='UPDATE' and old.role='cil_admin' and
 (new.id<>old.id or new.role<>old.role or new.entity_id<>old.entity_id or not new.active or new.email<>old.email) then
  raise exception 'The singleton administrator is immutable';
 end if;
 select kind into k from public.entities where id=new.entity_id;
 select user_id into admin_id from public.central_admin where singleton=true;
 if new.role='cil_admin' and (admin_id is null or new.id<>admin_id or k<>'holding') then raise exception 'Invalid administrator binding'; end if;
 if new.role='cmpdi' and k<>'technical' then raise exception 'CMPDI role requires technical entity'; end if;
 if new.role='subsidiary' and k<>'operating' then raise exception 'Subsidiary role requires operating entity'; end if;
 return new;
end $$;
create trigger guard_profile before insert or update or delete on public.profiles for each row execute function private.guard_profile();
create function private.guard_entity() returns trigger language plpgsql set search_path='' as $$
begin
 if TG_OP='UPDATE' and (new.code<>old.code or new.kind<>old.kind or new.parent_id is distinct from old.parent_id) then raise exception 'Entity identity is immutable'; end if;
 if new.kind='holding' and (new.code<>'CIL' or not new.active) then raise exception 'CIL must remain active'; end if;
 if new.kind<>'holding' and not exists(select 1 from public.entities where id=new.parent_id and kind='holding') then raise exception 'Subsidiaries must belong to CIL'; end if;
 if new.kind='technical' and new.code<>'CMPDI' then raise exception 'Technical entity must be CMPDI'; end if;
 return new;
end $$;
create trigger guard_entity before insert or update on public.entities for each row execute function private.guard_entity();

insert into public.entities(id,code,name,kind,location) values ('10000000-0000-0000-0000-000000000000','CIL','Coal India Limited','holding','Kolkata');
insert into public.entities(code,name,kind,parent_id,location) values
 ('ECL','Eastern Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Sanctoria'),
 ('BCCL','Bharat Coking Coal Limited','operating','10000000-0000-0000-0000-000000000000','Dhanbad'),
 ('CCL','Central Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Ranchi'),
 ('NCL','Northern Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Singrauli'),
 ('WCL','Western Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Nagpur'),
 ('SECL','South Eastern Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Bilaspur'),
 ('MCL','Mahanadi Coalfields Limited','operating','10000000-0000-0000-0000-000000000000','Sambalpur'),
 ('CMPDI','Central Mine Planning & Design Institute Limited','technical','10000000-0000-0000-0000-000000000000','Ranchi');

-- Service-only commands. auth users can never grant themselves a profile or role.
create function public.bootstrap_admin(p_user_id uuid,p_name text) returns uuid language plpgsql security definer set search_path='' as $$
declare existing uuid; addr text;
begin
 perform pg_advisory_xact_lock(876341);
 select email into addr from auth.users where id=p_user_id and email_confirmed_at is not null;
 if addr is null then raise exception 'Confirmed Auth user required'; end if;
 select user_id into existing from public.central_admin where singleton=true;
 if existing is not null and existing<>p_user_id then raise exception 'An administrator already exists'; end if;
 insert into public.central_admin(singleton,user_id) values(true,p_user_id) on conflict do nothing;
 insert into public.profiles(id,email,full_name,role,entity_id,must_change_password)
 values(p_user_id,addr,p_name,'cil_admin','10000000-0000-0000-0000-000000000000',false) on conflict(id) do nothing;
 if not exists(select 1 from public.profiles where id=p_user_id and role='cil_admin') then raise exception 'Existing non-admin profile cannot be promoted'; end if;
 return p_user_id;
end $$;
create function private.require_admin(p_actor uuid) returns void language plpgsql set search_path='' as $$
begin
 if not exists(select 1 from public.profiles p join public.central_admin a on a.user_id=p.id where p.id=p_actor and p.active and p.role='cil_admin' and not p.must_change_password) then raise exception 'Administrator required'; end if;
end $$;
create function public.provision_member(p_actor uuid,p_user_id uuid,p_name text,p_entity uuid) returns uuid language plpgsql security definer set search_path='' as $$
declare k public.entity_kind; addr text;
begin
 perform private.require_admin(p_actor);
 select kind into k from public.entities where id=p_entity and active for update;
 if k is null or k='holding' then raise exception 'Active subsidiary required'; end if;
 select email into addr from auth.users where id=p_user_id;
 if addr is null then raise exception 'Auth user required'; end if;
 insert into public.profiles(id,email,full_name,role,entity_id,must_change_password) values
 (p_user_id,addr,p_name,case when k='technical' then 'cmpdi'::public.app_role else 'subsidiary'::public.app_role end,p_entity,true);
 insert into public.access_events(actor_id,action,target) values(p_actor,'member.created',addr);
 return p_user_id;
end $$;
create function public.set_member_active(p_actor uuid,p_user_id uuid,p_active boolean) returns void language plpgsql security definer set search_path='' as $$
begin
 perform private.require_admin(p_actor);
 update public.profiles set active=p_active where id=p_user_id and role<>'cil_admin';
 if not found then raise exception 'Member not found or protected'; end if;
 insert into public.access_events(actor_id,action,target) values(p_actor,case when p_active then 'member.enabled' else 'member.disabled' end,p_user_id::text);
end $$;
create function public.finish_password_change(p_user_id uuid) returns void language plpgsql security definer set search_path='' as $$
begin
 update public.profiles set must_change_password=false where id=p_user_id and active;
 insert into public.access_events(actor_id,action,target) values(p_user_id,'password.changed',p_user_id::text);
end $$;
create function public.save_entity(p_actor uuid,p_entity uuid,p_code text,p_name text,p_location text,p_active boolean) returns uuid language plpgsql security definer set search_path='' as $$
declare result uuid;
begin
 perform private.require_admin(p_actor);
 if p_entity is null then
  insert into public.entities(code,name,kind,parent_id,location,active) values(p_code,p_name,'operating','10000000-0000-0000-0000-000000000000',p_location,p_active) returning id into result;
 else
  update public.entities set name=p_name,location=p_location,active=p_active where id=p_entity and kind<>'holding' returning id into result;
  if result is null then raise exception 'Entity not found or protected'; end if;
 end if;
 insert into public.access_events(actor_id,action,target) values(p_actor,'entity.saved',result::text);
 return result;
end $$;
revoke execute on function public.bootstrap_admin(uuid,text),public.provision_member(uuid,uuid,text,uuid),public.set_member_active(uuid,uuid,boolean),public.finish_password_change(uuid),public.save_entity(uuid,uuid,text,text,text,boolean) from public, anon, authenticated;
grant execute on function public.bootstrap_admin(uuid,text),public.provision_member(uuid,uuid,text,uuid),public.set_member_active(uuid,uuid,boolean),public.finish_password_change(uuid),public.save_entity(uuid,uuid,text,text,text,boolean) to service_role;
revoke execute on function private.require_admin(uuid),private.guard_profile(),private.guard_entity() from public, anon, authenticated;
commit;
