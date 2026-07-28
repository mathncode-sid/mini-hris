from datetime import date, datetime, timedelta
import calendar
import re
import sqlite3
import os

from flask import Flask, Response, g, jsonify, request
import csv
from io import StringIO


app = Flask(__name__, static_folder='static', static_url_path='')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('HR_SYSTEM_DATABASE', os.path.join(BASE_DIR, 'hr_system.sqlite'))

MIN_NOTICE_DAYS = 7
PAID_LEAVE_DAYS_PER_YEAR = 20
ESCALATION_DAYS = 3
MIN_TEAM_COVERAGE_RATIO = 0.5
PERIOD_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/')
def index():
    return app.send_static_file('index.html')


def parse_iso_date(value, field_name):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError(f'{field_name} must use YYYY-MM-DD format')


def inclusive_days(start, end):
    return (end - start).days + 1


def overlap_days(start_a, end_a, start_b, end_b):
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    if end < start:
        return 0
    return inclusive_days(start, end)


def cents_percent(amount_cents, basis_points):
    return amount_cents * basis_points // 10000


def row_to_dict(row):
    return dict(row) if row else None


def leave_days_for_year(db, employee_id, year, include_pending=True):
    statuses = ("'approved'", "'pending'") if include_pending else ("'approved'",)
    rows = db.execute(f'''
        SELECT start_date, end_date FROM leave_requests
        WHERE employee_id = ?
          AND is_paid = 1
          AND status IN ({','.join(statuses)})
    ''', (employee_id,)).fetchall()

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    total = 0
    for row in rows:
        total += overlap_days(
            parse_iso_date(row['start_date'], 'start_date'),
            parse_iso_date(row['end_date'], 'end_date'),
            year_start,
            year_end,
        )
    return total


def team_coverage_error(db, employee, start, end, ignored_request_id=None):
    team_rows = db.execute('''
        SELECT id FROM employees
        WHERE team = ? AND is_active = 1
    ''', (employee['team'],)).fetchall()
    team_size = len(team_rows)
    min_available = max(1, int((team_size * MIN_TEAM_COVERAGE_RATIO) + 0.9999))

    if team_size <= min_available:
        return None

    team_ids = [row['id'] for row in team_rows]
    placeholders = ','.join('?' for _ in team_ids)
    params = team_ids + [end.isoformat(), start.isoformat()]
    ignored_clause = ''
    if ignored_request_id is not None:
        ignored_clause = 'AND id != ?'
        params.append(ignored_request_id)

    existing_leave = db.execute(f'''
        SELECT id, employee_id, start_date, end_date
        FROM leave_requests
        WHERE employee_id IN ({placeholders})
          AND status IN ('pending', 'approved')
          AND start_date <= ?
          AND end_date >= ?
          {ignored_clause}
    ''', params).fetchall()

    for offset in range(inclusive_days(start, end)):
        day = start + timedelta(days=offset)
        out = {employee['id']}
        for leave in existing_leave:
            leave_start = parse_iso_date(leave['start_date'], 'start_date')
            leave_end = parse_iso_date(leave['end_date'], 'end_date')
            if leave_start <= day <= leave_end:
                out.add(leave['employee_id'])

        available = team_size - len(out)
        if available < min_available:
            return (
                f'Coverage violation: {employee["team"]} would have only '
                f'{available} of {team_size} active employees available on {day.isoformat()}.'
            )
    return None


def validate_leave_request(db, employee_id, start, end, is_paid):
    if end < start:
        return 'End date cannot be before start date'

    notice_days = (start - date.today()).days
    if notice_days < MIN_NOTICE_DAYS:
        return (
            f'Policy violation: leave requests require at least '
            f'{MIN_NOTICE_DAYS} days notice to protect team coverage.'
        )

    employee = row_to_dict(db.execute('''
        SELECT * FROM employees WHERE id = ? AND is_active = 1
    ''', (employee_id,)).fetchone())
    if not employee:
        return 'Employee must exist and be active'

    overlap = db.execute('''
        SELECT id FROM leave_requests
        WHERE employee_id = ?
          AND status IN ('pending', 'approved')
          AND start_date <= ?
          AND end_date >= ?
    ''', (employee_id, end.isoformat(), start.isoformat())).fetchone()
    if overlap:
        return 'Leave request overlaps an existing pending or approved request'

    if is_paid:
        requested_days = inclusive_days(start, end)
        used_days = leave_days_for_year(db, employee_id, start.year)
        if start.year != end.year:
            return 'Paid leave requests must stay within one calendar year'
        if used_days + requested_days > PAID_LEAVE_DAYS_PER_YEAR:
            return (
                f'Leave balance exceeded: {employee["name"]} has '
                f'{PAID_LEAVE_DAYS_PER_YEAR - used_days} paid days remaining.'
            )

    return team_coverage_error(db, employee, start, end)


@app.route('/api/employees', methods=['GET'])
def get_employees():
    db = get_db()
    cursor = db.execute('''
        SELECT e.id, e.name, e.role, e.team, e.start_date, e.salary_cents,
               e.employment_type, e.is_active, m.name as manager_name
        FROM employees e
        LEFT JOIN employees m ON e.manager_id = m.id
        WHERE e.is_active = 1
        ORDER BY e.team, e.manager_id IS NOT NULL, e.name
    ''')
    return jsonify([dict(row) for row in cursor.fetchall()])


@app.route('/api/employees/<int:employee_id>/deactivate', methods=['POST'])
def deactivate_employee(employee_id):
    db = get_db()
    employee = db.execute('''
        SELECT id, name, is_active FROM employees WHERE id = ?
    ''', (employee_id,)).fetchone()
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404
    if not employee['is_active']:
        return jsonify({'error': 'Employee is already inactive'}), 400

    direct_reports = db.execute('''
        SELECT COUNT(*) AS total
        FROM employees
        WHERE manager_id = ? AND is_active = 1
    ''', (employee_id,)).fetchone()['total']
    if direct_reports:
        return jsonify({
            'error': 'Reassign active direct reports before deactivating this manager'
        }), 400

    db.execute('UPDATE employees SET is_active = 0 WHERE id = ?', (employee_id,))
    db.commit()
    return jsonify({'message': f'{employee["name"]} deactivated'})


@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    db = get_db()
    today = date.today()
    upcoming_end = today + timedelta(days=30)

    employees = db.execute('SELECT COUNT(*) AS total FROM employees WHERE is_active = 1').fetchone()['total']
    pending = db.execute("SELECT COUNT(*) AS total FROM leave_requests WHERE status = 'pending'").fetchone()['total']
    out_soon = db.execute('''
        SELECT l.start_date, l.end_date, e.name, e.team
        FROM leave_requests l
        JOIN employees e ON e.id = l.employee_id
        WHERE l.status = 'approved'
          AND l.start_date <= ?
          AND l.end_date >= ?
        ORDER BY l.start_date
        LIMIT 6
    ''', (upcoming_end.isoformat(), today.isoformat())).fetchall()
    overdue = db.execute('''
        SELECT COUNT(*) AS total
        FROM leave_requests
        WHERE status = 'pending'
          AND date(created_at) <= date('now', ?)
    ''', (f'-{ESCALATION_DAYS} days',)).fetchone()['total']

    balances = []
    for row in db.execute('SELECT id, name FROM employees WHERE is_active = 1 ORDER BY name'):
        used = leave_days_for_year(db, row['id'], today.year, include_pending=True)
        balances.append({
            'employee_id': row['id'],
            'employee_name': row['name'],
            'used_days': used,
            'remaining_days': max(0, PAID_LEAVE_DAYS_PER_YEAR - used),
        })

    return jsonify({
        'active_employees': employees,
        'pending_approvals': pending,
        'escalations': overdue,
        'out_soon': [dict(row) for row in out_soon],
        'leave_balances': balances,
    })


@app.route('/api/leave', methods=['POST'])
def request_leave():
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    is_paid = 1 if data.get('is_paid', 1) else 0
    reason = (data.get('reason') or '').strip()

    if not all([employee_id, start_date_str, end_date_str]):
        return jsonify({'error': 'Employee, start date, and end date are required'}), 400

    try:
        employee_id = int(employee_id)
        start = parse_iso_date(start_date_str, 'start_date')
        end = parse_iso_date(end_date_str, 'end_date')
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400

    db = get_db()
    error = validate_leave_request(db, employee_id, start, end, is_paid)
    if error:
        return jsonify({'error': error}), 400

    db.execute('''
        INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid, reason)
        VALUES (?, ?, ?, 'pending', ?, ?)
    ''', (employee_id, start.isoformat(), end.isoformat(), is_paid, reason))
    db.commit()

    return jsonify({'message': 'Leave requested successfully'}), 201


@app.route('/api/leave/<int:request_id>/approve', methods=['POST'])
def approve_leave(request_id):
    db = get_db()
    leave = db.execute('''
        SELECT l.*, e.team, e.name
        FROM leave_requests l
        JOIN employees e ON e.id = l.employee_id
        WHERE l.id = ?
    ''', (request_id,)).fetchone()
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404
    if leave['status'] != 'pending':
        return jsonify({'error': 'Only pending leave requests can be approved'}), 400

    employee = row_to_dict(db.execute('SELECT * FROM employees WHERE id = ?', (leave['employee_id'],)).fetchone())
    start = parse_iso_date(leave['start_date'], 'start_date')
    end = parse_iso_date(leave['end_date'], 'end_date')
    error = team_coverage_error(db, employee, start, end, ignored_request_id=request_id)
    if error:
        return jsonify({'error': error}), 400

    db.execute('''
        UPDATE leave_requests
        SET status = 'approved', decided_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (request_id,))
    db.commit()
    return jsonify({'message': 'Leave approved'})


@app.route('/api/leave/<int:request_id>/reject', methods=['POST'])
def reject_leave(request_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    cursor = db.execute('''
        UPDATE leave_requests
        SET status = 'rejected', rejection_reason = ?, decided_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'pending'
    ''', ((data.get('reason') or '').strip(), request_id))
    db.commit()
    if cursor.rowcount == 0:
        return jsonify({'error': 'Pending leave request not found'}), 404
    return jsonify({'message': 'Leave rejected'})


def calculate_taxes(taxable_cents):
    tax = 0
    remaining = max(0, taxable_cents)

    brackets = [
        (80000000, 3500),
        (50000000, 3250),
        (3233300, 3000),
        (2400000, 2500),
        (0, 1000),
    ]
    for floor, rate in brackets:
        if remaining > floor:
            tax += cents_percent(remaining - floor, rate)
            remaining = floor

    return max(0, tax - 240000)


def calculate_payslip(employee, period_start, period_end, days_in_month, unpaid_leave_rows):
    monthly_gross = employee['salary_cents'] // 12
    daily_rate = monthly_gross // days_in_month
    employee_start = parse_iso_date(employee['start_date'], 'start_date')

    payable_days = days_in_month
    if employee_start > period_start:
        payable_days = 0 if employee_start > period_end else inclusive_days(employee_start, period_end)

    unpaid_days_seen = set()
    for leave in unpaid_leave_rows:
        leave_start = parse_iso_date(leave['start_date'], 'start_date')
        leave_end = parse_iso_date(leave['end_date'], 'end_date')
        for offset in range(overlap_days(leave_start, leave_end, period_start, period_end)):
            day = max(leave_start, period_start) + timedelta(days=offset)
            if employee_start <= day <= period_end:
                unpaid_days_seen.add(day)

    unpaid_leave_days = min(payable_days, len(unpaid_days_seen))
    paid_days = max(0, payable_days - unpaid_leave_days)
    gross = daily_rate * paid_days
    nssf = cents_percent(min(gross, 3600000), 600)
    taxable = max(0, gross - nssf)
    paye = calculate_taxes(taxable)
    shif = cents_percent(gross, 275)
    housing = cents_percent(gross, 150)
    deductions = nssf + paye + shif + housing

    return {
        'gross_pay_cents': gross,
        'deductions_cents': deductions,
        'net_pay_cents': gross - deductions,
        'nssf_cents': nssf,
        'paye_cents': paye,
        'shif_cents': shif,
        'housing_levy_cents': housing,
        'taxable_income_cents': taxable,
        'unpaid_leave_days': unpaid_leave_days,
        'payable_days': payable_days,
    }


@app.route('/api/payroll/generate', methods=['POST'])
def generate_payroll():
    data = request.get_json(silent=True) or {}
    period = data.get('period')
    if not period or not PERIOD_RE.match(period):
        return jsonify({'error': 'Period is required in YYYY-MM format'}), 400

    year, month = map(int, period.split('-'))
    _, days_in_month = calendar.monthrange(year, month)
    period_start = date(year, month, 1)
    period_end = date(year, month, days_in_month)

    db = get_db()
    employees = db.execute('''
        SELECT * FROM employees
        WHERE is_active = 1 AND start_date <= ?
        ORDER BY name
    ''', (period_end.isoformat(),)).fetchall()

    db.execute('DELETE FROM payslips WHERE period = ?', (period,))
    processed_records = []

    for employee in employees:
        leave_rows = db.execute('''
            SELECT start_date, end_date FROM leave_requests
            WHERE employee_id = ?
              AND status = 'approved'
              AND is_paid = 0
              AND start_date <= ?
              AND end_date >= ?
        ''', (employee['id'], period_end.isoformat(), period_start.isoformat())).fetchall()
        payslip = calculate_payslip(employee, period_start, period_end, days_in_month, leave_rows)

        db.execute('''
            INSERT INTO payslips (
                employee_id, period, gross_pay_cents, deductions_cents, net_pay_cents,
                nssf_cents, paye_cents, shif_cents, housing_levy_cents,
                taxable_income_cents, unpaid_leave_days, payable_days
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            employee['id'], period, payslip['gross_pay_cents'], payslip['deductions_cents'],
            payslip['net_pay_cents'], payslip['nssf_cents'], payslip['paye_cents'],
            payslip['shif_cents'], payslip['housing_levy_cents'],
            payslip['taxable_income_cents'], payslip['unpaid_leave_days'], payslip['payable_days'],
        ))
        processed_records.append({
            'employee': employee['name'],
            'gross_cents': payslip['gross_pay_cents'],
            'net_cents': payslip['net_pay_cents'],
        })

    db.commit()
    return jsonify({
        'message': f'Payroll generated for {period}',
        'records_processed': len(processed_records),
        'summary': processed_records,
    }), 201


@app.route('/api/leave', methods=['GET'])
def get_leave_requests():
    db = get_db()
    cursor = db.execute('''
        SELECT l.id, l.employee_id, l.start_date, l.end_date, l.status, l.is_paid,
               l.reason, l.rejection_reason, l.created_at,
               date(l.created_at) <= date('now', ?) AS needs_escalation,
               e.name as employee_name, e.team
        FROM leave_requests l
        JOIN employees e ON l.employee_id = e.id
        ORDER BY l.status = 'pending' DESC, l.start_date DESC
    ''', (f'-{ESCALATION_DAYS} days',))
    return jsonify([dict(row) for row in cursor.fetchall()])


@app.route('/api/payroll', methods=['GET'])
def get_payroll():
    period = request.args.get('period')
    if not period or not PERIOD_RE.match(period):
        return jsonify({'error': 'Period is required in YYYY-MM format'}), 400

    db = get_db()
    cursor = db.execute('''
        SELECT p.*, e.name as employee_name
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.period = ?
        ORDER BY e.name
    ''', (period,))
    return jsonify([dict(row) for row in cursor.fetchall()])


@app.route('/api/payroll/export', methods=['GET'])
def export_payroll_csv():
    period = request.args.get('period')
    if not period or not PERIOD_RE.match(period):
        return jsonify({'error': 'Period is required in YYYY-MM format'}), 400

    db = get_db()
    rows = db.execute('''
        SELECT e.name AS employee_name, e.role, e.team, p.period,
               p.gross_pay_cents, p.nssf_cents, p.paye_cents, p.shif_cents,
               p.housing_levy_cents, p.deductions_cents, p.net_pay_cents,
               p.payable_days, p.unpaid_leave_days, p.generated_at
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.period = ?
        ORDER BY e.name
    ''', (period,)).fetchall()

    if not rows:
        return jsonify({'error': f'No generated payroll found for {period}'}), 404

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'period', 'employee_name', 'role', 'team', 'gross_kes', 'nssf_kes',
        'paye_kes', 'shif_kes', 'housing_levy_kes', 'total_deductions_kes',
        'net_pay_kes', 'payable_days', 'unpaid_leave_days', 'generated_at',
    ])
    for row in rows:
        writer.writerow([
            row['period'],
            row['employee_name'],
            row['role'],
            row['team'],
            f'{row["gross_pay_cents"] / 100:.2f}',
            f'{row["nssf_cents"] / 100:.2f}',
            f'{row["paye_cents"] / 100:.2f}',
            f'{row["shif_cents"] / 100:.2f}',
            f'{row["housing_levy_cents"] / 100:.2f}',
            f'{row["deductions_cents"] / 100:.2f}',
            f'{row["net_pay_cents"] / 100:.2f}',
            row['payable_days'],
            row['unpaid_leave_days'],
            row['generated_at'],
        ])

    filename = f'payroll-{period}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
