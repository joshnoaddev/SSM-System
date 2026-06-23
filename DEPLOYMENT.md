# SSM local deployment checklist

## One-time database setup

1. Open the Supabase SQL editor.
2. Run `database/001_transactional_imports.sql`.
3. Confirm `app_audit_log` exists and all four RPC functions are available.
4. Export a database backup and verify that it can be restored.

## Workbook policy

- Assign one computer as the workbook editor.
- Other computers should use Supabase screens and exports; do not edit the same
  network workbook concurrently.
- The app creates timestamped copies in `SSM Backups` beside the workbook and
  retains the ten newest copies.

## Build

Run from PowerShell:

```powershell
.\build_release.ps1
```

Upload the generated `dist\SSM_Student_Profiling.exe` to GitHub Releases or
another public direct-download file host. Supabase Storage is not used for the
compiled executable because the file is larger than the dashboard upload limit.

After the file is uploaded, publish the update URL to Supabase:

```powershell
.\.venv\Scripts\python.exe .\publish_update.py --download-url "https://github.com/0superweak/SSM-System/releases/download/v1.0.1/SSM_Student_Profiling.exe"
```

Use the real release URL and version tag for the build you uploaded. Do not copy
a developer Python environment to the other computers.

## Smoke test on every computer

1. Launch the executable and verify database connection.
2. Open Students; search, filter by area, and scroll past 50 records.
3. Open one profile and verify its photo.
4. Add a clearly marked test student, edit it, then remove it from Supabase.
5. Add and delete a test expense.
6. Open the workbook and confirm the correct path for that computer.
7. Verify the operator name before making changes.
8. Confirm an entry appears in `app_audit_log`.

## Release rule

Deploy only from a clean Git commit after tests pass. Keep the previous release
folder for rollback until the new build has run successfully on all three PCs.
