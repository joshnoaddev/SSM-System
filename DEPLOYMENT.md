# SSM local deployment checklist

## First launch

The desktop application must use a Supabase **publishable/anon** key with Row
Level Security enabled. Never ship an `sb_secret_` or service-role key in source
code or inside the executable.

On first launch, the application opens **Connect this computer**. Enter the
project URL and publishable/anon key from the Supabase dashboard. The application
stores these non-secret settings for the current Windows user in:

```text
%APPDATA%\SSM Student Profiling\config.json
```

No rebuild, command prompt, or Windows environment-variable setup is required.
To replace a damaged or outdated configuration, rename or delete that file and
launch the application again.

Environment variables remain available for managed deployments and override the
saved user configuration:

```powershell
$env:SSM_SUPABASE_URL = "https://your-project.supabase.co"
$env:SSM_SUPABASE_PUBLISHABLE_KEY = "your-publishable-key"
```

Rotate any secret key that has previously been committed or packaged before
distributing a new build.

## One-time database setup

1. Open the Supabase SQL editor.
2. Run `database/001_transactional_imports.sql`.
3. Run `database/002_google_sheet_sync.sql`.
4. Confirm `app_audit_log` and all four transactional RPC functions are
   available.
5. Confirm Row Level Security is enabled on the application tables and the
   `student-photos` bucket is private.
6. Export a database backup and verify that it can be restored.

This is a shared-office access model with no email/password login. The
publishable key can access application data through the configured RLS policies,
and the operator selected at startup is written to the audit log. Keep the
executable and `%APPDATA%\SSM Student Profiling\config.json` within the office;
do not publish the configuration file.

## Google Sheets synchronization

Deploy the `sync-google-sheet` Edge Function and configure its Google service
account credentials, workbook ID, Supabase service key, and
`SSM_SHEET_SYNC_TOKEN` as server-side secrets. The private sync token should be
at least 32 random characters and must be different from every Supabase key.

On each office computer:

1. Open **Settings**.
2. Paste the same private value into **Google Sheets synchronization**.
3. Select **Save changes**.
4. Return to the Dashboard and select **Sync now**.
5. Confirm that the success state shows students, donors, movements, and
   coordinators, then verify the new `Google Sheets Sync` entry in
   `app_audit_log`.

Windows encrypts this token for the current Windows user before saving it to the
local configuration. It is not bundled into the executable and is not stored in
plain text.

If the function gateway returns `401` while the desktop app uses a current
`sb_publishable_` key, disable legacy JWT verification for only this Edge
Function and redeploy it. The function still rejects every commit request that
does not contain the correct `x-ssm-sync-token`; keep that custom token
requirement enabled.

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
$env:SSM_SUPABASE_SERVICE_KEY = "your-secret-service-role-key"
.\.venv\Scripts\python.exe .\publish_update.py --download-url "https://github.com/0superweak/SSM-System/releases/download/v1.0.1/SSM_Student_Profiling.exe"
```

Use the real release URL and version tag for the build you uploaded. Do not copy
a developer Python environment to the other computers. Configure the service
key only on the administrator's build computer, never on application PCs.

## Smoke test on every computer

1. Launch the executable, complete first-run setup if prompted, select one of
   the three office profiles, and verify the dashboard opens.
2. Open Students; search, filter by area, and scroll past 50 records.
3. Open one profile and verify its photo.
4. Add a clearly marked test student, edit it, then remove it from Supabase.
5. Add and delete a test expense.
6. Open the workbook and confirm the correct path for that computer.
7. Select each office profile in turn and verify the displayed name.
8. Run **Sync now** from the Dashboard and verify the record counts.
9. Turn on **Use larger interface text**, restart the app, and verify the
   Dashboard and Settings remain readable at the minimum window size.
10. Turn on **Reduce interface motion** and verify page changes no longer fade.
11. Confirm an entry appears in `app_audit_log`.

## Release rule

Deploy only from a clean Git commit after tests pass. Keep the previous release
folder for rollback until the new build has run successfully on all three PCs.
