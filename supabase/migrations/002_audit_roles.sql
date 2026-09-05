begin;
create type public.review_position as enum ('contributor','assistant_manager','manager');
alter table public.profiles add column review_position public.review_position not null default 'contributor';

create function public.set_review_position(p_actor uuid,p_user_id uuid,p_position public.review_position) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform private.require_admin(p_actor);
 update public.profiles set review_position=p_position where id=p_user_id and role='subsidiary';
 if not found then raise exception 'Subsidiary member required'; end if;
 insert into public.access_events(actor_id,action,target) values(p_actor,'member.review_position',p_user_id::text||':'||p_position::text);
end $$;
revoke all on function public.set_review_position(uuid,uuid,public.review_position) from public;
grant execute on function public.set_review_position(uuid,uuid,public.review_position) to service_role;
commit;
