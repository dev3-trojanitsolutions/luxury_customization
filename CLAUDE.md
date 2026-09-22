# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## App Overview

`luxury_customization` is a Frappe v16 custom app extending ERPNext with employee management, check-in, and company document tracking features. It runs within the bench at `/home/trojan-technologies/frappe-bench` on site `local.com`.

**⚠️ Important:** Do not directly edit vendored apps (`frappe`, `erpnext`, `hrms`). All customizations must stay within this app, using hooks, overrides, or middleware.

## Common Commands

All commands run from `/home/trojan-technologies/frappe-bench`.

```bash
# Build JS/CSS assets for this app
bench build --app luxury_customization

# Run all tests for this app
bench --site local.com run-tests --app luxury_customization

# Run a specific test module
bench --site local.com run-tests --module luxury_customization.luxury_customization.doctype.company_documents.test_company_documents

# Run database migrations after DocType or custom field changes
bench --site local.com migrate

# Clear cache (required after hooks.py or custom field changes)
bench --site local.com clear-cache

# Run the daily scheduler task manually (company document expiry notifications)
bench --site local.com execute luxury_customization.tasks.send_company_document_expiry_notifications

# Install/uninstall the app
bench --site local.com install-app luxury_customization
bench --site local.com uninstall-app luxury_customization
```

## Linting and Formatting

From `apps/luxury_customization/` (after `pre-commit install`):

```bash
# Run all pre-commit hooks on staged files
pre-commit run

# Run on all files
pre-commit run --all-files

# Run ruff linter only
ruff check luxury_customization/

# Run ruff formatter only
ruff format luxury_customization/
```

Config: `pyproject.toml` (line length: 110, indent: tabs, Python 3.14+). ESLint uses `.eslintrc` with `eslint:recommended` base, prettier for JS/Vue/SCSS, and pyupgrade for Python.

## Architecture

### Directory Structure

```
luxury_customization/
├── customizations/          # Custom field definitions (hooks)
│   ├── employee.py         # WPS fields (wps_required, wps_id)
│   ├── company.py          # Company logo & notification settings
│   └── employee_checkin.py # Employee code & image fields, auto-set checkin time
├── luxury_customization/
│   ├── doctype/
│   │   └── company_documents/  # New DocType: document tracking with expiry dates
│   ├── web_form/
│   │   └── employee_checkin/   # Public-facing web form for employee check-ins
│   └── api/
│       └── employee_checkin.py # Whitelisted API for fetching employee details
├── public/js/
│   └── company.js          # Frontend customizations for Company doctype
├── hooks.py                # App configuration (doc_events, scheduler_events, custom fields)
└── tasks.py                # Scheduled tasks (send company document expiry notifications)
```

### Core Features

**1. Custom Fields (created via `after_migrate` hook)**
- **Employee:** `wps_required`, `wps_id` (payroll tracking)
- **Company:** `company_logos`, `notify_days`, `notify_userd` (document expiry notifications)
- **Employee Checkin:** `employee_code` (read-only), `employee_image` (attach image)

**2. Company Documents DocType**
- Tracks documents with expiry dates
- Linked to Company for notification settings
- Fields: `company`, `document_name`, `expiry_date`, etc.

**3. Employee Checkin Flow**
- Doc event hook `before_insert` auto-sets `time` field to current datetime
- Web form `employee-checkin` provides public check-in submission
- Custom `employee_code` and `employee_image` fields auto-populate from selected employee
- API endpoint `get_employee_details` returns `employee_name`, `employee_number` given an employee link

**4. Daily Scheduler Task**
- Checks Company Documents approaching expiry
- Uses `notify_days` (days before expiry) and `notify_userd` (user list) from Company record
- Sends both bell notifications (Notification Log) and emails
- Deduplicates by document name, user, and same-day creation

### Custom Field Lifecycle

- `after_install` → creates custom fields
- `after_migrate` → re-creates if missing
- `after_uninstall` → deletes custom fields
- Lookup: `{"dt": doctype, "fieldname": field_name}`

## Workflow Typical Changes

- **Adding a custom field:** Edit `customizations/*.py`, add field dict, run `bench --site local.com migrate`
- **Modifying Company Documents:** Update `luxury_customization/doctype/company_documents/company_documents.json` (JSON) and `.py` (controller logic), run `bench --site local.com migrate`
- **Updating the Employee Checkin web form:** Edit `web_form/employee_checkin/employee_checkin.json` (field definitions), run `bench --site local.com clear-cache`
- **Changing notification logic:** Edit `tasks.py`, test with `bench --site local.com execute luxury_customization.tasks.send_company_document_expiry_notifications`
- **Frontend customizations:** Edit `public/js/company.js`, run `bench build --app luxury_customization`

## Database and Cache

- Custom fields are stored in `tabCustom Field` (Frappe's meta-data store)
- After changes to `customizations/*.py` or `hooks.py`: always run `bench --site local.com clear-cache`
- After DocType JSON changes: run `bench --site local.com migrate`
- The scheduler reads live Company and Company Documents records; changes take effect immediately after save (no cache invalidation needed for scheduler logic)
