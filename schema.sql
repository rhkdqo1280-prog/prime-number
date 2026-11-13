create table public.prime_rosters (
  classroom text primary key,
  names text[] not null
);
create table public.prime_rounds (
  code text primary key,
  classroom text not null,
  names text[] not null,
  board integer[] not null,
  answer integer[] not null,
  created_at timestamptz not null default now()
);
create table public.prime_attempts (
  id bigint generated always as identity primary key,
  code text not null references public.prime_rounds(code) on delete cascade,
  student text not null,
  correct boolean not null,
  submitted_at timestamptz not null default clock_timestamp(),
  unique(code, student)
);
create index prime_attempts_ranking on public.prime_attempts(code, id) where correct;

alter table public.prime_rosters enable row level security;
alter table public.prime_rounds enable row level security;
alter table public.prime_attempts enable row level security;
revoke all on public.prime_rosters, public.prime_rounds, public.prime_attempts from public, anon, authenticated;
grant select, insert, update on public.prime_rosters to service_role;
grant select, insert on public.prime_rounds to service_role;
grant select, insert on public.prime_attempts to service_role;
grant usage on sequence public.prime_attempts_id_seq to service_role;

create function public.prime_submit(p_code text, p_student text, p_picks integer[])
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  game public.prime_rounds%rowtype;
  attempt public.prime_attempts%rowtype;
  place bigint;
begin
  -- Serialize submissions within each round so the displayed ranks stay stable.
  select * into game from public.prime_rounds where code = p_code for update;
  if not found or not coalesce(p_student = any(game.names), false) then
    return jsonb_build_object('status', 'denied');
  end if;
  if coalesce(cardinality(p_picks), 0) <> 9
    or (select count(distinct n) from unnest(p_picks) as n) <> 9
    or not (p_picks <@ game.board) then
    return jsonb_build_object('status', 'invalid');
  end if;

  select * into attempt from public.prime_attempts
  where code = p_code and student = p_student;
  if not found then
    insert into public.prime_attempts(code, student, correct)
    values (p_code, p_student, p_picks <@ game.answer)
    returning * into attempt;
  end if;

  if not attempt.correct then
    return jsonb_build_object('status', 'wrong');
  end if;
  select count(*) into place from public.prime_attempts
  where code = p_code and correct and id <= attempt.id;
  return jsonb_build_object('status', 'correct', 'rank', place);
end;
$$;
-- SELECT FOR UPDATE requires UPDATE privilege on at least one column.
grant update (code) on public.prime_rounds to service_role;
revoke all on function public.prime_submit(text, text, integer[]) from public, anon, authenticated;
grant execute on function public.prime_submit(text, text, integer[]) to service_role;
