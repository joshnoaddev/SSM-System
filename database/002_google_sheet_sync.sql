-- Run after 001_transactional_imports.sql and the Google Sheet metadata
-- columns migration. This server-only RPC applies a complete workbook sync in
-- one database transaction so partial imports are rolled back automatically.

begin;

create or replace function public.sync_google_workbook_transactional(
    p_students jsonb,
    p_donor_school_year text,
    p_donor_students jsonb,
    p_movements jsonb,
    p_coordinators jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    student_count integer := 0;
    donor_count integer := 0;
    movement_count integer := 0;
    coordinator_count integer := 0;
    resolved_donors jsonb := '[]'::jsonb;
    resolved_movements jsonb := '[]'::jsonb;
begin
    if auth.role() <> 'service_role' then
        raise exception 'Google Sheet sync requires the service role'
            using errcode = '42501';
    end if;

    if jsonb_typeof(p_students) <> 'array'
       or jsonb_array_length(p_students) = 0 then
        raise exception 'Student sync payload is empty or invalid';
    end if;
    if jsonb_typeof(p_donor_students) <> 'array'
       or jsonb_typeof(p_movements) <> 'array'
       or jsonb_typeof(p_coordinators) <> 'array' then
        raise exception 'Workbook relationship payload is invalid';
    end if;

    -- Preserve identity when a source row already belongs to a synced student
    -- whose name or other details changed in Google Sheets.
    update public.students s
    set last_name = p.last_name,
        first_name = p.first_name,
        gender = p.gender,
        grade = p.grade,
        address = p.address,
        city = p.city,
        area = p.area,
        birthday = nullif(trim(p.birthday), ''),
        sponsor = p.sponsor,
        contact = p.contact,
        school = p.school,
        parents = p.parents,
        course = p.course,
        remarks = p.remarks,
        status = coalesce(nullif(p.status, ''), 'Active'),
        source_sheet_name = p.source_sheet_name,
        source_row_number = p.source_row_number,
        sheet_synced_at = now()
    from jsonb_to_recordset(p_students) as p(
        last_name text,
        first_name text,
        gender text,
        grade text,
        address text,
        city text,
        area text,
        birthday text,
        sponsor text,
        contact text,
        school text,
        parents text,
        course text,
        remarks text,
        status text,
        source_student_id text,
        source_sheet_name text,
        source_row_number integer
    )
    where p.source_student_id is not null
      and s.source_student_id = p.source_student_id;

    student_count := public.import_students_transactional(p_students);

    -- Attach Google source metadata after the duplicate-safe student import.
    update public.students s
    set source_student_id = p.source_student_id,
        source_sheet_name = p.source_sheet_name,
        source_row_number = p.source_row_number,
        sheet_synced_at = now()
    from jsonb_to_recordset(p_students) as p(
        last_name text,
        first_name text,
        birthday text,
        source_student_id text,
        source_sheet_name text,
        source_row_number integer
    )
    where lower(trim(s.last_name)) = lower(trim(p.last_name))
      and lower(trim(s.first_name)) = lower(trim(p.first_name))
      and (
          nullif(trim(p.birthday), '') is null
          or nullif(trim(s.birthday), '') is not distinct from
             nullif(trim(p.birthday), '')
      );

    -- The Edge Function sends canonical masterlist names for every linked
    -- donor row. Resolve those names only after student inserts/updates finish.
    select coalesce(
        jsonb_agg(
            jsonb_build_object(
                'school_year', p_donor_school_year,
                'donor_name', d.donor_name,
                'student_id', matched.id,
                'location', d.location,
                'level', d.level,
                'sponsor', d.sponsor,
                'remarks', d.remarks
            )
        ),
        '[]'::jsonb
    )
    into resolved_donors
    from jsonb_to_recordset(p_donor_students) as d(
        donor_name text,
        student_last_name text,
        student_first_name text,
        location text,
        level text,
        sponsor text,
        remarks text
    )
    join lateral (
        select s.id
        from public.students s
        where lower(trim(s.last_name)) =
              lower(trim(d.student_last_name))
          and lower(trim(s.first_name)) =
              lower(trim(d.student_first_name))
        order by s.id
        limit 1
    ) matched on true;

    if jsonb_array_length(resolved_donors) <>
       jsonb_array_length(p_donor_students) then
        raise exception 'One or more donor students could not be resolved';
    end if;

    select coalesce(
        jsonb_agg(
            jsonb_build_object(
                'category', m.category,
                'student_id', matched.id,
                'location', m.location,
                'level', m.level,
                'remarks', m.remarks
            )
        ),
        '[]'::jsonb
    )
    into resolved_movements
    from jsonb_to_recordset(p_movements) as m(
        category text,
        student_last_name text,
        student_first_name text,
        location text,
        level text,
        remarks text
    )
    join lateral (
        select s.id
        from public.students s
        where lower(trim(s.last_name)) =
              lower(trim(m.student_last_name))
          and lower(trim(s.first_name)) =
              lower(trim(m.student_first_name))
        order by s.id
        limit 1
    ) matched on true;

    if jsonb_array_length(resolved_movements) <>
       jsonb_array_length(p_movements) then
        raise exception 'One or more movement students could not be resolved';
    end if;

    donor_count := public.replace_donor_students_transactional(
        p_donor_school_year,
        resolved_donors
    );
    movement_count := public.replace_student_movements_transactional(
        resolved_movements
    );
    coordinator_count := public.replace_coordinators_transactional(
        p_coordinators
    );

    insert into public.app_audit_log (
        operator,
        action,
        entity_type,
        details
    )
    values (
        'Google Sheets Sync',
        'synchronize',
        'workbook',
        jsonb_build_object(
            'students', student_count,
            'donor_students', donor_count,
            'movements', movement_count,
            'coordinators', coordinator_count,
            'donor_school_year', p_donor_school_year
        )
    );

    return jsonb_build_object(
        'students', student_count,
        'donor_students', donor_count,
        'movements', movement_count,
        'coordinators', coordinator_count
    );
end;
$$;

revoke all on function public.sync_google_workbook_transactional(
    jsonb,
    text,
    jsonb,
    jsonb,
    jsonb
) from public, anon, authenticated;

grant execute on function public.sync_google_workbook_transactional(
    jsonb,
    text,
    jsonb,
    jsonb,
    jsonb
) to service_role;

commit;
