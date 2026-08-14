# SSM Student Profiling

A Windows desktop application for the Student Support Ministry office. It keeps
student records, sponsorships, expenses, and coordinator assignments in one
place, backed by Supabase and synchronized with the office Excel workbook and a
Google Sheet.

The app is an internal operational tool for a small shared office. It is not a
public service and has no per-user login; the operator picks a profile at
startup and every action is written to an audit log.

## Features

- **Students** — searchable, filterable list with photos, profile details,
  sponsor and coordinator assignment, and archiving.
- **Dashboard** — office-wide counts, budget status, and one-click sync.
- **Expenses** — per-student and yearly budget tracking with a receipt ledger.
- **Workbook** — reads and writes the office Excel workbook, keeping timestamped
  backups in an `SSM Backups` folder beside it.
- **Coordinators** — area coordinator records and assignment.
- **Activity log and archive** — recoverable workflows and an audit trail.
- **Google Sheets sync** — pulls students, donors, movements, and coordinators
  through a Supabase Edge Function.
- Light and dark themes, larger-text mode, and a reduced-motion mode.

## Requirements

- Windows 10 or 11
- Python 3.12
- A Supabase project with Row Level Security enabled

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

On first launch the app opens **Connect this computer**. Enter the Supabase
project URL and the project's **publishable/anon** key. Settings are saved per
Windows user to `%APPDATA%\SSM Student Profiling\config.json`.

Never configure a secret or service-role key in the desktop app. Those keys
belong only on the administrator's build machine, as environment variables, and
are only used by the release scripts.

Copy `.env.example` to `.env` if you prefer environment variables; environment
values override the saved configuration.

## Database

Run the migrations in `database/` against the Supabase SQL editor in order:
`001_transactional_imports.sql`, `002_google_sheet_sync.sql`,
`003_office_workflows.sql`. Confirm RLS is enabled on the application tables and
that the `student-photos` bucket is private.

Full deployment, sync, and smoke-test steps are in [DEPLOYMENT.md](DEPLOYMENT.md).

## Tests

```powershell
python -m unittest tests.test_regressions
```

CI runs the same suite on every push to `main` (`.github/workflows/build.yml`)
with `QT_QPA_PLATFORM=offscreen`, then builds the executable.

## Build

```powershell
.\build_release.ps1
```

The signed-off executable lands in `dist\`. Release output, the virtual
environment, and any exported spreadsheet are intentionally not tracked by Git.

## Project layout

```
app.py                  main window and most screens
office_app/
  app_config.py         configuration and credential resolution
  repositories/         Supabase data access
  services/             business logic, sync, import/export, updater
  ui/                   theme tokens, shared components, extracted views
  utils/                background tasks, path helpers
assets/                 icons, fonts, QSS stylesheet
database/               SQL migrations
supabase/functions/     Google Sheets sync Edge Function
tests/                  regression suite
tools/                  developer and import utilities
```

## Data handling

This repository must never contain student data. Student names, addresses,
birthdays, contact numbers, and photos are personal information about minors and
belong only in Supabase and the office workbook. Exported spreadsheets are
ignored by Git; do not force-add them.

## Contributing

See [CLAUDE_UI_HANDOFF.md](CLAUDE_UI_HANDOFF.md) for the current UI work in
progress, the module layout, and the guardrails that apply to interface changes.
