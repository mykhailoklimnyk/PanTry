create table products (
    external_product_id text primary key,
    name                text not null,
    slug                text,
    category            text,
    unit                text,
    step                numeric(6, 3),
    weight_g            integer,
    nutrition           jsonb,
    delisted_at         timestamptz,
    last_seen_at        timestamptz,
    created_at          timestamptz not null default now()
);

create index products_category_idx on products (category);

create type receipt_source as enum ('offline', 'online');

create table receipts (
    id                    uuid primary key default uuidv7(),
    source                receipt_source not null,
    external_id           text not null,
    purchased_at          timestamptz not null,
    branch_id             text,
    trip_day              date,
    total                 numeric(10, 2),
    discount_total        numeric(10, 2),
    bonuses_accrued       numeric(10, 2),
    is_cancelled          boolean not null default false,
    receipt_url           text,
    raw                   jsonb,
    imported_at           timestamptz not null default now(),
    unique (source, external_id)
);

create index receipts_purchased_at_idx on receipts (purchased_at desc);
create index receipts_trip_idx on receipts (trip_day, branch_id);

create table receipt_lines (
    id                   bigint generated always as identity primary key,
    receipt_id           uuid not null references receipts (id) on delete cascade,
    external_product_id  text references products (external_product_id),
    name_at_purchase     text not null,
    qty                  numeric(10, 3) not null,
    price                numeric(10, 2),
    discount             numeric(10, 2),
    is_promo             boolean not null default false,
    removed              boolean not null default false,
    is_service           boolean not null default false,
    catalog_price_at_import numeric(10, 2),
    rewards              jsonb
);

create index receipt_lines_receipt_idx on receipt_lines (receipt_id);
create index receipt_lines_product_idx on receipt_lines (external_product_id)
    where is_service = false;

create table consumption_cycles (
    external_product_id  text primary key references products (external_product_id),
    purchases_count      integer not null,
    median_interval_days numeric(6, 2),
    stddev_days          numeric(6, 2),
    reorder_probability  numeric(4, 3),
    confidence           numeric(4, 3) not null,
    is_stable            boolean not null default false,
    last_purchased_at    timestamptz,
    next_expected_at     timestamptz,
    updated_at           timestamptz not null default now()
);

create type correction_action as enum ('still_have', 'ran_out_earlier', 'never_again');

create table user_corrections (
    id                  bigint generated always as identity primary key,
    external_product_id text not null references products (external_product_id),
    action              correction_action not null,
    agent_run_id        uuid,
    created_at          timestamptz not null default now()
);

create index user_corrections_product_idx on user_corrections (external_product_id, created_at desc);

create type substitution_source as enum ('history', 'replacements', 'similar', 'manual');

create table substitution_rules (
    external_product_id      text not null references products (external_product_id),
    rank                     smallint not null,
    replacement_external_id  text not null references products (external_product_id),
    source                   substitution_source not null,
    accepted_count           integer not null default 0,
    rejected_count           integer not null default 0,
    updated_at               timestamptz not null default now(),
    primary key (external_product_id, replacement_external_id)
);

create index substitution_rules_rank_idx on substitution_rules (external_product_id, rank);

create table order_validations (
    id           uuid primary key default uuidv7(),
    order_id     text not null,
    receipt_id   uuid references receipts (id),
    validated_at timestamptz not null default now(),
    unique (order_id)
);

create type line_outcome as enum ('as_ordered', 'substituted', 'missing');
create type line_feedback as enum ('ok', 'wrong');

create table order_line_outcomes (
    id                  bigint generated always as identity primary key,
    order_id            text not null,
    external_product_id text not null references products (external_product_id),
    outcome             line_outcome not null,
    substituted_with    text references products (external_product_id),
    user_feedback       line_feedback,
    feedback_at         timestamptz
);

create index order_line_outcomes_order_idx on order_line_outcomes (order_id);

create table phantom_events (
    id                  bigint generated always as identity primary key,
    occurred_at         timestamptz not null,
    external_product_id text not null references products (external_product_id),
    branch_id           text,
    stock_at_order      integer,
    order_id            text
);

create index phantom_events_product_idx on phantom_events (external_product_id, occurred_at desc);

create type shelf_life_level as enum ('auto', 'strict', 'none');

create table shelf_life_requests (
    id                  bigint generated always as identity primary key,
    order_id            text not null,
    external_product_id text not null references products (external_product_id),
    required_until_date date not null,
    level               shelf_life_level not null default 'auto',
    created_at          timestamptz not null default now()
);

create type run_mode as enum ('demo', 'live');

create table agent_runs (
    id          uuid primary key default uuidv7(),
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    mode        run_mode not null,
    model       text,
    tokens_in   integer,
    tokens_out  integer,
    cost_usd    numeric(10, 6),
    duration_ms integer,
    ok          boolean,
    error       text
);

create table agent_steps (
    id             bigint generated always as identity primary key,
    run_id         uuid not null references agent_runs (id) on delete cascade,
    seq            integer not null,
    tool_name      text not null,
    args_redacted  jsonb,
    duration_ms    integer,
    result_summary text,
    decision_text  text,
    external_product_id text,
    ok             boolean not null default true,
    created_at     timestamptz not null default now(),
    unique (run_id, seq)
);

create index agent_steps_product_idx on agent_steps (run_id, external_product_id);


create table watched_carts (
    cart_id         uuid primary key,
    branch_id       text,
    slot_start      timestamptz not null,
    slot_end        timestamptz,
    chains          jsonb not null default '{}'::jsonb,
    mandates        jsonb not null default '{}'::jsonb,
    handed_at       timestamptz not null default now(),
    last_checked_at timestamptz,
    released_at     timestamptz,
    release_reason  text
);

create index watched_carts_due_idx on watched_carts (slot_start)
    where released_at is null;

create table revalidations (
    id                  bigint generated always as identity primary key,
    cart_id             uuid not null references watched_carts (cart_id) on delete cascade,
    checked_at          timestamptz not null default now(),
    external_product_id text,
    verdict             text,
    action              text not null,
    note                text,
    ok                  boolean not null default true
);

create index revalidations_cart_idx on revalidations (cart_id, checked_at desc);


alter table watched_carts
    add column access_sealed     bytea,
    add column access_expires_at timestamptz,
    add column access_fingerprint text,
    add column granted_at        timestamptz;


create table if not exists newcomers (
    account    text primary key,

    first_seen timestamptz not null default now(),

    greeted_at timestamptz
);

create index if not exists newcomers_first_seen_idx on newcomers (first_seen);


create table if not exists categories (
    id         text primary key,
    parent_id  text,
    slug       text not null,
    title      text not null,
    first_seen timestamptz not null default now(),
    last_seen  timestamptz not null default now(),

    gone_at    timestamptz
);

create index if not exists categories_parent_idx on categories (parent_id);

create index if not exists categories_title_idx on categories (lower(title));


create table if not exists intent_names (
    name_sha   text primary key,

    intent     text not null,
    subtype    text,

    first_seen timestamptz not null default now(),
    last_seen  timestamptz not null default now()
);


create table if not exists pantry_marks (
    account   text        not null,

    kind      text        not null,

    stocked_at timestamptz not null,

    said_at   timestamptz not null default now(),

    primary key (account, kind)
);


create table if not exists guest_rules (
    account  text        not null,

    rule_id  text        not null,

    label    text        not null,

    active   boolean     not null default true,

    added_at timestamptz not null default now(),
    said_at  timestamptz not null default now(),

    primary key (account, rule_id)
);


alter table agent_runs drop column if exists mode;
drop type if exists run_mode;

alter table agent_runs add column if not exists account text not null default '';

alter table agent_runs add column if not exists owner text not null default '';

alter table agent_runs add column if not exists kind text not null default 'basket';

create index if not exists agent_runs_started_idx on agent_runs (started_at);
create index if not exists agent_runs_account_idx on agent_runs (account, started_at);

alter table watched_carts add column if not exists account text not null default '';

drop table if exists revalidations;
drop table if exists watched_carts;


alter table intent_names add column if not exists drink text;


create table if not exists pantry_items (
    account  text        not null,

    kind     text        not null,

    label    text        not null,

    added_at timestamptz not null default now(),

    primary key (account, kind)
);


create table if not exists pantry_cycles (
    account  text        not null,

    kind     text        not null,

    days     integer     not null check (days >= 1),

    said_at  timestamptz not null default now(),

    primary key (account, kind)
);


create table if not exists intent_keeps (
    label_sha text        not null primary key,

    keeps     text        not null,

    last_seen timestamptz not null default now()
);


create table if not exists catalog_nodes (
    article    text        not null primary key,

    nodes      text[]      not null,

    first_seen timestamptz not null default now(),
    last_seen  timestamptz not null default now(),

    gone_at    timestamptz
);

create index if not exists catalog_nodes_last_seen_idx on catalog_nodes (last_seen);


alter table catalog_nodes add column if not exists name     text;
alter table catalog_nodes add column if not exists name_key text;

create index if not exists catalog_nodes_name_key_idx on catalog_nodes (name_key);


alter table catalog_nodes add column if not exists product_id    text;
alter table catalog_nodes add column if not exists slug          text;
alter table catalog_nodes add column if not exists company_id    text;
alter table catalog_nodes add column if not exists weighted      boolean;
alter table catalog_nodes add column if not exists sale_step     numeric;
alter table catalog_nodes add column if not exists display_ratio text;

create index if not exists catalog_nodes_product_id_idx on catalog_nodes (product_id);


create table if not exists pantry_sources (
    account    text        not null,

    scope      text        not null,

    mode       text        not null,

    said_at    timestamptz not null default now(),

    primary key (account, scope)
);


alter table pantry_items
    add column if not exists scope text not null default 'pantry';

alter table pantry_items
    drop constraint if exists pantry_items_pkey;

alter table pantry_items
    add primary key (account, scope, kind);


create table if not exists wanted_items (
    account  text        not null,

    kind     text        not null,

    label    text        not null,

    added_at timestamptz not null default now(),

    primary key (account, kind)
);


alter table wanted_items
    add column if not exists at_home boolean not null default true;


create table if not exists saved_swaps (
    account  text        not null,

    kind     text        not null,

    label    text        not null,

    chain    jsonb       not null,

    saved_at timestamptz not null default now(),

    primary key (account, kind)
);

alter table agent_runs
    add column if not exists payer text not null default 'project';


create table if not exists pantry_hidden (
    account text not null,

    kind    text not null,

    said_at timestamptz not null default now(),

    primary key (account, kind)
);


do $$
begin
    if exists (
        select 1 from information_schema.columns
         where table_schema = current_schema()
           and table_name = 'receipts'
           and column_name = 'external_id'
    ) then
        -- Разом із двома таблицями 0001, які на неї посилаються ключем і
        -- яких код теж не пише (0 рядків на проді 02.09): без них drop
        -- відмовляє на залежностях -- саме так упав CI на свіжій базі.
        if exists (select 1 from receipts)
            or exists (select 1 from receipt_lines)
            or exists (select 1 from order_validations) then
            raise exception 'receipts з 0001 не порожня: перенести руками до 0026';
        end if;
        drop table receipt_lines;
        drop table order_validations;
        drop table receipts;
    end if;
end $$;

create table if not exists receipts (
    account    text not null,

    source     text not null,

    ident      text not null,

    bought_at  timestamptz not null,

    payload    jsonb not null,

    active     boolean not null default true,

    seen_at    timestamptz not null default now(),

    primary key (account, source, ident)
);

create index if not exists receipts_by_account
    on receipts (account, source, bought_at desc)
    where active;

create table if not exists receipt_reads (
    account   text not null,
    source    text not null,

    last_at   timestamptz,

    read_at   timestamptz not null default now(),

    primary key (account, source)
);

alter table pantry_items
    add column if not exists origin text not null default 'guest';

update pantry_items
   set origin = 'purchases'
 where origin = 'guest'
   and label like '% · %';

update pantry_items p
   set origin = 'purchases'
  from intent_names i
 where p.origin = 'guest'
   and (
        lower(p.label) = lower(i.intent)
     or (i.subtype is not null and i.subtype <> ''
         and lower(p.label) = lower(i.intent || ' · ' || i.subtype))
   );

alter table wanted_items
    add column if not exists origin text not null default 'guest';

alter table wanted_items
    add column if not exists why text;

create table if not exists intent_sense (
    label_sha  text        primary key,
    sanity     text        not null,
    rhythm_lies boolean    not null,
    made_at    timestamptz not null default now(),
    last_seen  timestamptz not null default now()
);

create table if not exists intent_facts (
    label_sha  text        primary key,
    keeps      text,
    sanity     text,
    rhythm_lies boolean,
    per_day    numeric(12, 4),
    per_day_unit text,
    made_at    timestamptz not null default now(),
    last_seen  timestamptz not null default now()
);

insert into intent_facts (label_sha, keeps, made_at, last_seen)
select label_sha, keeps, last_seen, last_seen from intent_keeps
on conflict (label_sha) do update set keeps = excluded.keeps;

insert into intent_facts (label_sha, sanity, rhythm_lies, made_at, last_seen)
select label_sha, sanity, rhythm_lies, made_at, last_seen from intent_sense
on conflict (label_sha) do update
   set sanity      = excluded.sanity,
       rhythm_lies = excluded.rhythm_lies;


update intent_names set intent = 'цукерки' where intent = 'цукерка';
update intent_names set intent = 'напій газований' where intent = 'газований напій';
update intent_names set intent = 'тістечко' where intent = 'тістечка';
update intent_names set intent = 'напій енергетичний' where intent = 'енергетичний напій';
update intent_names set intent = 'сир кисломолочний' where intent = 'кисломолочний сир';
update intent_names set intent = 'туалетний папір' where intent = 'папір туалетний';
update intent_names set intent = 'свічка декоративна' where intent = 'свічки декоративні';
update intent_names set intent = 'батончик шоколадний' where intent = 'шоколадний батончик';
update intent_names set intent = 'напій слабоалкогольний' where intent = 'слабоалкогольний напій';
update intent_names set intent = 'батарейки' where intent = 'батарейка';
update intent_names set intent = 'зубна паста' where intent = 'паста зубна';
update intent_names set intent = 'снеки' where intent = 'снек';
update intent_names set intent = 'сирок глазурований' where intent = 'глазурований сирок';
update intent_names set intent = 'ковбаски' where intent = 'ковбаска';
update intent_names set intent = 'батончик злаковий' where intent = 'злаковий батончик';
update intent_names set intent = 'палички крабові' where intent = 'крабові палички';
update intent_names set intent = 'прокладки гігієнічні' where intent = 'гігієнічні прокладки';
update intent_names set intent = 'батончик протеїновий' where intent = 'протеїновий батончик';
update intent_names set intent = 'молочний коктейль' where intent = 'коктейль молочний';
update intent_names set intent = 'льодяник' where intent = 'льодяники';
update intent_names set intent = 'зубна щітка' where intent = 'щітка зубна';
update intent_names set intent = 'напій соковий' where intent = 'соковий напій';
update intent_names set intent = 'контейнер для зберігання' where intent = 'контейнери для зберігання';
update intent_names set intent = 'пюре дитяче' where intent = 'дитяче пюре';
update intent_names set intent = 'котлети' where intent = 'котлета';
update intent_names set intent = 'паста горіхова' where intent = 'горіхова паста';
update intent_names set intent = 'картридж для фільтра-глечика' where intent = 'картриджі для фільтра-глечика';
update intent_names set intent = 'філе куряче' where intent = 'куряче філе';
update intent_names set intent = 'пончик' where intent = 'пончики';
update intent_names set intent = 'серветка для прибирання' where intent = 'серветки для прибирання';
update intent_names set intent = 'снек дитячий' where intent = 'снеки дитячі';
update intent_names set intent = 'булочка' where intent = 'булочки';
update intent_names set intent = 'дитяча книга' where intent = 'книга дитяча';
update intent_names set intent = 'огірки' where intent = 'огірок';
update intent_names set intent = 'пакети' where intent = 'пакет';
update intent_names set intent = 'сирники' where intent = 'сирник';
update intent_names set intent = 'палички ватні' where intent = 'ватні палички';
update intent_names set intent = 'резинка для волосся' where intent = 'резинки для волосся';
update intent_names set intent = 'паста арахісова' where intent = 'арахісова паста';
update intent_names set intent = 'ватні диски' where intent = 'диски ватні';
update intent_names set intent = 'трубочки вафельні' where intent = 'вафельні трубочки';
update intent_names set intent = 'прикраса декоративна' where intent = 'прикраси декоративні';
update intent_names set intent = 'суміш горіхів і сухофруктів' where intent = 'суміш сухофруктів і горіхів';
update intent_names set intent = 'сушка' where intent = 'сушки';
update intent_names set intent = 'курячі крильця' where intent = 'крильця курячі';
update intent_names set intent = 'кукурудзяні снеки' where intent = 'снеки кукурудзяні';
update intent_names set intent = 'овочі' where intent = 'овоч';
update intent_names set intent = 'фрукт сушений' where intent = 'фрукти сушені';
update intent_names set intent = 'груші' where intent = 'груша';
update intent_names set intent = 'десерт рослинний' where intent = 'рослинний десерт';
update intent_names set intent = 'крило куряче' where intent = 'куряче крило';
update intent_names set intent = 'кульки повітряні' where intent = 'кулька повітряна';
update intent_names set intent = 'леза для бритви' where intent = 'лезо для бритви';
update intent_names set intent = 'насіння соняшника' where intent = 'насіння соняшнику';
update intent_names set intent = 'аксесуар карнавальний' where intent = 'карнавальний аксесуар';
update intent_names set intent = 'банани' where intent = 'банан';
update intent_names set intent = 'квашена капуста' where intent = 'капуста квашена';
update intent_names set intent = 'прикраса карнавальна' where intent = 'карнавальна прикраса';
update intent_names set intent = 'кунжутна паста' where intent = 'паста кунжутна';
update intent_names set intent = 'склянки' where intent = 'склянка';
update intent_names set intent = 'сухі сніданки' where intent = 'сухий сніданок';
update intent_names set intent = 'ялинка штучна' where intent = 'штучна ялинка';
update intent_names set intent = 'аксесуар для волосся' where intent = 'аксесуари для волосся';
update intent_names set intent = 'анчоус' where intent = 'анчоуси';
update intent_names set intent = 'баклажан' where intent = 'баклажани';
update intent_names set intent = 'батончик вафельний' where intent = 'вафельний батончик';
update intent_names set intent = 'батончик енергетичний' where intent = 'енергетичний батончик';
update intent_names set intent = 'блок для унітаза' where intent = 'блок для унітазу';
update intent_names set intent = 'кабачки' where intent = 'кабачок';
update intent_names set intent = 'маса сиркова' where intent = 'сиркова маса';
update intent_names set intent = 'нектарин' where intent = 'нектарини';
update intent_names set intent = 'пюре томатне' where intent = 'томатне пюре';
update intent_names set intent = 'тост' where intent = 'тости';

update intent_names set subtype = 'без кісточок' where intent = 'виноград' and subtype = 'без кісточки';
update intent_names set subtype = 'копчена' where intent = 'м''ясний виріб' and subtype = 'копчений';
update intent_names set subtype = 'дитяче' where intent = 'набір прикрас для подарунків' and subtype = 'дитячий';
update intent_names set subtype = 'жіноче' where intent = 'набір прикрас для подарунків' and subtype = 'жіночий';
update intent_names set subtype = 'чорні в''ялені' where intent = 'оливки' and subtype = 'в''ялені чорні';
update intent_names set subtype = 'до грилю' where intent = 'приправа' and subtype = 'до гриля';
update intent_names set subtype = 'анчоус' where intent = 'риба консервована' and subtype = 'анчоуси';
update intent_names set subtype = 'з індичатиною' where intent = 'сосиски' and subtype = 'з індичатини';

update intent_names set subtype = 'пальчикова' where intent = 'батарейки' and subtype = 'пальчикові';
update intent_names set subtype = 'шоколадний' where intent = 'пончик' and subtype = 'шоколадні';
update intent_names set subtype = 'вологопоглинаюча' where intent = 'серветка для прибирання' and subtype = 'вологопоглинаючі';
update intent_names set subtype = 'еклер' where intent = 'тістечко' and subtype = 'еклери';
update intent_names set subtype = 'заварне' where intent = 'тістечко' and subtype = 'заварні';
update intent_names set subtype = 'птіфури' where intent = 'тістечко' and subtype = 'птіфур';
update intent_names set subtype = 'шоколадне' where intent = 'тістечко' and subtype = 'шоколадні';
update intent_names set subtype = 'марципанові' where intent = 'цукерки' and subtype = 'марципан';

update intent_names set subtype = null where intent = 'молоко' and subtype = '1%';
update intent_names set subtype = null where intent = 'молоко' and subtype = '2,5%';
update intent_names set subtype = null where intent = 'молоко' and subtype = '3,2%';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'жирність 2,5%';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'жирне';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'знежирене';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'низькожирне';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'середньої жирності';
update intent_names set subtype = null where intent = 'молоко' and subtype = 'незбиране';

update intent_names set subtype = 'tawny'
 where subtype ~ '^[а-яіїєґ]+wny$';

update intent_names set subtype = null where intent = 'напій енергетичний' and subtype = 'zoom';

update intent_names set subtype = '2 в 1' where subtype = '2в1';

update intent_names set subtype = null where intent = 'суміш горіхів і сухофруктів' and subtype = 'з Омега-3';


create table if not exists pantry_splits (
    account text not null,

    scope   text not null default 'pantry',

    intent  text not null,

    said_at timestamptz not null default now(),

    primary key (account, scope, intent)
);


create table if not exists pantry_drinks (
    account text not null,

    kind    text not null,

    grp     text not null,

    said_at timestamptz not null default now(),

    primary key (account, kind)
);


alter table intent_facts add column if not exists aisle text;

alter table pantry_cycles
  add column if not exists said boolean not null default true,
  add column if not exists from_kind text;

comment on column pantry_cycles.said is
  'true -- число назвав гість; false -- розклав агент з його відповіді (#386)';
comment on column pantry_cycles.from_kind is
  'Вид, відповідь про який дала це число. NULL -- гість назвав його прямо.';
