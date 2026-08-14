# Claude UI Handoff

_Last refreshed: 2026-08-14 (verified against the working tree at commit `4ba7d18`)._

## Goal

Continue modernizing the SSM desktop app UI while keeping the app stable for current users.

Primary ask: visual polish and interaction improvements, not business-logic changes.

## Current State

- The app is a PyQt6 desktop application rooted at `app.py` (~7,400 lines; it still owns most screens).
- The UI has two overlapping directions: a Figma-derived design system driven by `office_app/ui/theme.py` + `assets/styles/app.qss`, and `qfluentwidgets` accessed only through the adapter.
- `office_app/ui/fluent.py` is the shared `qfluentwidgets` adapter with PyQt fallbacks. It sets `HAS_FLUENT` and falls back to plain PyQt widgets when the library is missing.
- Light/dark tokens live in `office_app/ui/theme.py`. QSS uses `@token` placeholders that `render_qss()` in `app.py` expands, since Qt QSS has no variables.
- Extracted views: student list, settings, activity log, archive. Everything else is still built inline in `app.py`.

## Package Layout

```
office_app/ui/
  __init__.py                  exports ActionButton, Card, EmptyState, Spacing,
                               StatusBadge, set_content_hugging_button,
                               DESIGN_TOKENS, theme_color
  components.py                small reusable widgets (Card, EmptyState, badges)
  configuration_dialog.py      first-run / configuration dialog
  fluent.py                    qfluentwidgets adapter + PyQt fallbacks
  motion.py                    reduced-motion-aware animation helpers
  theme.py                     LIGHT_THEME / DARK_THEME tokens, Spacing,
                               set_active_theme, get_active_theme_tokens,
                               set_large_text, theme_color
  views/
    __init__.py                exports StudentListView
    activity_log_view.py
    archive_view.py
    settings_figma_view.py     defines SettingsView (Figma-aligned settings page)
    student_list_model.py      custom delegate that paints student cards
    student_list_view.py
```

Note: there is no `office_app/ui/views/settings_view.py`. An earlier version of this handoff referred to that path; the live module is `settings_figma_view.py`, imported in `app.py` as
`from office_app.ui.views.settings_figma_view import SettingsView`. A stale `settings_view.cpython-312.pyc` still sits in `views/__pycache__/` and can be ignored.

## Important Entry Points in `app.py`

| Symbol | Line (approx.) | Notes |
| --- | --- | --- |
| `create_sidebar` | 2201 | dispatches to legacy or Fluent sidebar |
| `_create_legacy_sidebar` | 2208 | PyQt fallback navigation |
| `_create_fluent_sidebar` | 2395 | Fluent navigation shell |
| `create_dashboard_screen` | 2898 | metric cards + list sections |
| `_create_profile_screen_legacy` | 3935 | superseded, still present |
| `create_profile_screen` | 4155 | current profile surface |
| `create_add_screen` | 4411 | |
| `create_expenses_screen` | 4549 | budget status, ledger table |
| `create_coordinators_screen` | 4888 | CRUD layout |
| `create_settings_screen` | 4978 | hosts `SettingsView` |
| `create_workbook_screen` | 5258 | toolbar + worksheet table |

`StudentApp.change_theme()` calls `set_active_theme()` and re-applies the stylesheet; it also syncs qfluent theme state. `render_qss()` expands `@token` names longest-first so `@primary` does not partially consume `@primary_hover`.

Responsive behavior: the window is considered compact below 1120px width. In compact mode the header subtitle, the header eyebrow, and the `HeaderMark` accent bar are hidden, the sync panel grows to 126px, and `SettingsView.set_compact(True)` is called.

## Uncommitted Work in the Tree

Three files are modified relative to `HEAD` (`4ba7d18`), all cosmetic:

- `office_app/ui/theme.py` — retuned light-theme brand, surface, text, border, and sidebar hex values; `radius_md` 8px → 9px, `radius_lg` 12px → 14px.
- `assets/styles/app.qss` — matching radius bumps (7/8/11px → 9/12/13px), heavier header weights (700 → 750), taller `WorkspaceHeader` (48–54px → 60–68px), secondary-button surface/hover retint, new `DashboardMetricCard[tone="success"|"graduated"|"danger"]` rules.
- `app.py` — added the `HeaderMark` accent bar (3×38px) to the workspace header, un-hid `HeaderEyebrow`, tightened page-body spacing 26 → 22, and wired eyebrow/mark visibility into the compact-mode handler.

Decide whether to commit or revert these before starting a new polish pass, so a fresh diff stays readable.

## Suggested UI Improvement Focus

1. **Dashboard** — modernize summary cards and list sections; improve visual hierarchy and spacing. Keep it operational, not marketing-like.
2. **Profile screen** — clean up the details grid, action buttons, remarks section, and profile completion display. Make destructive actions visually clear but not overwhelming.
3. **Expenses screen** — improve budget status, progress feedback, table density, and add-expense controls. Keep finance data easy to scan.
4. **Workbook screen** — improve toolbar grouping and worksheet/table affordances; preserve existing workbook behavior.
5. **Coordinators screen** — modernize CRUD layout and action states.
6. **Extraction (optional)** — dashboard, expenses, workbook, and coordinators are still inline in `app.py`. Extracting one at a time into `office_app/ui/views/` follows the pattern already set by the student list and settings views.

## Guardrails

- Do not remove the PyQt fallback behavior in `office_app/ui/fluent.py`.
- Do not import `qfluentwidgets` directly from individual views; go through the adapter.
- Do not make database, import, or repository changes while working only on UI polish.
- Avoid large rewrites of `app.py` unless extracting a view is clearly safer.
- Be careful when styling generic `QPushButton` or `QLabel` in `app.qss`; those rules also reach Fluent widgets.
- Keep cards at modest radii and avoid nested cards.
- The app is an operational tool; prioritize scanability, density, and predictable controls.
- Preserve tests and existing workflows.

## Validation

Regression suite, run on 2026-08-14:

```powershell
python -m unittest tests.test_regressions
```

Result:

```text
Ran 69 tests in 3.880s
OK
```

(The suite has grown from 19 tests at the time of the original handoff.)

Read-only compile check, useful because `python -m py_compile` hits a `__pycache__` permission issue in this workspace:

```powershell
python -c "import pathlib; files=['app.py','office_app/ui/fluent.py','office_app/ui/views/settings_figma_view.py','office_app/ui/views/student_list_view.py','office_app/ui/views/student_list_model.py']; [compile(pathlib.Path(f).read_text(encoding='utf-8-sig'), f, 'exec') for f in files]; print('compile ok')"
```

## Related Files

- `THEME_CHANGES.md` — a historical instruction sheet describing how theme switching was wired into `app.py` (imports, `render_qss`, `CircularProgress.paintEvent`, `change_theme`, `__init__` hookup). Those changes are already applied; keep it only as background reading.
- `claude-handoff.diff` — stale. It was exported on 26 June against a much older `HEAD` and its 17 files have long since been committed. Use `git diff` for the live picture rather than this file.

## Red Flags Already Fixed

- SQL migration adds `student_id` columns before using them.
- Student import no longer deletes students missing from a workbook payload.
- `qfluentwidgets` is optional through the adapter.
- The `QFont::setPointSize` warning in the student card delegate was fixed by sanitizing copied fonts before pixel sizing.
