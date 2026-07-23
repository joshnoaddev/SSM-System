-- SSM office workflow upgrade: recoverable records, expense review, receipts.
-- Safe to run more than once.

alter table public.students
    add column if not exists archived_at timestamptz,
    add column if not exists archived_by text;

alter table public.expenses
    add column if not exists archived_at timestamptz,
    add column if not exists archived_by text,
    add column if not exists category text not null default 'Other',
    add column if not exists approval_status text not null default 'Pending',
    add column if not exists receipt_url text,
    add column if not exists receipt_name text,
    add column if not exists approved_by text,
    add column if not exists approved_at timestamptz;

update public.expenses
set category = 'Other'
where category is null or btrim(category) = '';

update public.expenses
set approval_status = 'Pending'
where approval_status is null
   or approval_status not in ('Pending', 'Approved', 'Rejected');

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'expenses_approval_status_check'
          and conrelid = 'public.expenses'::regclass
    ) then
        alter table public.expenses
            add constraint expenses_approval_status_check
            check (approval_status in ('Pending', 'Approved', 'Rejected'));
    end if;
end
$$;

create index if not exists students_archived_at_idx
    on public.students (archived_at);
create index if not exists expenses_archived_at_idx
    on public.expenses (archived_at);
create index if not exists expenses_approval_status_idx
    on public.expenses (approval_status);
create index if not exists expenses_category_idx
    on public.expenses (category);

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'expense-receipts',
    'expense-receipts',
    true,
    10485760,
    array['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'SSM office can read expense receipts'
    ) then
        create policy "SSM office can read expense receipts"
            on storage.objects for select
            using (bucket_id = 'expense-receipts');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'SSM office can upload expense receipts'
    ) then
        create policy "SSM office can upload expense receipts"
            on storage.objects for insert
            with check (bucket_id = 'expense-receipts');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'SSM office can update expense receipts'
    ) then
        create policy "SSM office can update expense receipts"
            on storage.objects for update
            using (bucket_id = 'expense-receipts')
            with check (bucket_id = 'expense-receipts');
    end if;
end
$$;
