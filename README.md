# Mini-HRIS

A small internal HR and payroll tool built with Flask, SQLite, and vanilla HTML/CSS/JS.

The project focuses on the parts of the brief where correctness matters most: leave rules, manager approvals, payroll proration, repeatable payroll runs, and a dashboard that exposes operational state.

## What I Prioritized

I prioritized leave management and payroll depth over authentication or a large employee-admin module. The challenge asks for real business logic rather than broad CRUD, so the app spends most of its effort on policy checks and payroll calculations:

- Leave requests are validated for notice, date order, employee status, overlapping requests, annual paid leave balance, and team coverage.
- Managers can approve or reject pending requests.
- Unpaid approved leave reduces monthly gross pay.
- Payroll generation handles mid-month joiners, unpaid leave, zero tax cases, and salary values around tax bracket boundaries.
- Payroll generation is idempotent for a period: re-running a month replaces that month's payslips instead of duplicating them.
- The dashboard shows pending approvals, escalation count, upcoming absence, and leave balances.
- Two small stretch improvements are included: employee deactivation and payroll CSV export.

## Tech Stack

- Backend: Flask
- Frontend: HTML, CSS, vanilla JavaScript
- Database: SQLite
- Tests: Python `unittest`

## Data Model

The SQLite database contains:

- `employees`: employee profile, manager relationship, active flag, employment type, and salary in cents.
- `leave_requests`: paid/unpaid leave requests with pending, approved, and rejected statuses.
- `payslips`: generated monthly payslips with gross pay, deduction breakdown, net pay, payable days, and unpaid leave days.

Employees are deactivated with `is_active`; they are not deleted, so historical payroll records can still join back to employee records.

The Organization screen includes a deactivate action for active employees. Managers with active direct reports cannot be deactivated until those reports are reassigned, which prevents broken reporting lines.

The included `hr_system.sqlite` file acts as the sample database/dump and contains seeded employees, leave requests, and generated payslips for `2026-07`.

## Leave Rules

The app models a few problems that spreadsheet-based leave tracking often misses:

- Short-notice absence: requests must be submitted at least 7 days before the start date.
- Invalid date ranges: end date cannot be before start date.
- Double-booking: an employee cannot have overlapping pending or approved leave.
- Paid leave balance: each active employee has 20 paid leave days per calendar year. Pending and approved paid leave both reserve balance.
- Team coverage: for teams with enough staff, at least 50% of active team members must remain available on each requested day.
- Stale approvals: pending requests older than 3 days are surfaced as escalations on the dashboard.

Leave interacts with payroll through unpaid leave. Approved unpaid leave inside a payroll period reduces payable days and gross pay.

## Payroll Formula

All money is stored and calculated in cents using integer math.

Monthly gross pay:

```text
monthly_gross = annual_salary / 12
daily_rate = monthly_gross / days_in_month
gross_pay = daily_rate * payable_days_after_join_date_and_unpaid_leave
```

Simplified deduction model:

- NSSF-style social security: 6% of gross pay, capped at KES 36,000 gross.
- Taxable income: gross pay minus social security.
- PAYE-style progressive tax after KES 2,400 monthly relief:
  - 10% up to KES 24,000
  - 25% from KES 24,001 to KES 32,333
  - 30% from KES 32,334 to KES 500,000
  - 32.5% from KES 500,001 to KES 800,000
  - 35% above KES 800,000
- SHIF-style health deduction: 2.75% of gross pay.
- Housing levy: 1.5% of gross pay.

This is intentionally a simple assessment formula for the coding challenge, not a claim of production legal compliance for any country.

## How to Run Locally

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python init_db.py
python app.py
```

Open `http://127.0.0.1:5000`.

Running `python init_db.py` rebuilds `hr_system.sqlite` with sample employees, leave requests, and a generated `2026-07` payroll period.

## Stretch Features Added

- Employee deactivation: active employees can be deactivated from the Organization screen. Their historical leave and payslip records remain available.
- Payroll CSV export: generated payroll periods can be exported from the Payroll screen. The export includes employee, role, team, gross pay, NSSF, PAYE, SHIF, housing levy, total deductions, net pay, payable days, unpaid leave days, and generation timestamp.

## Tests

```bash
python -m unittest test_app.py
```

The test suite covers:

- PAYE zero-deduction and bracket-boundary math.
- 7-day notice validation.
- Invalid leave date order.
- Overlapping leave rejection.
- Paid leave balance rejection.
- Team coverage rejection.
- Rejection workflow.
- Payroll idempotency.
- Mid-month joiner proration with approved unpaid leave.
- Employee deactivation while preserving payslip history.
- Manager deactivation guard when direct reports are still active.
- Payroll CSV export for generated periods.

## UI Notes

The frontend is intentionally quiet and operations-focused:

- Dashboard first, not a marketing-style landing page.
- Employee dropdowns instead of raw ID entry.
- Dense tables for repeated HR workflows.
- Clear empty, loading, success, and error states.
- Responsive layout for smaller screens.
- Fetched data is rendered through DOM APIs instead of raw HTML string injection.

## What I Would Improve Next

- Add login and role-based access control so only managers/HR can approve leave or run payroll.
- Add employee create/edit screens and manager reassignment.
- Add PDF payslip exports.
- Add payroll finalization/locking after review.
- Add public holidays and working-day calendars instead of calendar-day proration.
- Add manager-specific approval queues instead of a global approval list.
