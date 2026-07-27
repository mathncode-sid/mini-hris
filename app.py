from flask import Flask, request, jsonify, g
import calendar
import sqlite3
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
DATABASE = 'hr_system.sqlite'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # Returns dict-like rows instead of tuples
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Serve the frontend
@app.route('/')
def index():
    return app.send_static_file('index.html')


# --- EMPLOYEE ROUTES ---

@app.route('/api/employees', methods=['GET'])
def get_employees():
    db = get_db()
    # Fetch active employees and join to get manager names for the UI
    cursor = db.execute('''
        SELECT e.id, e.name, e.role, e.team, e.start_date, e.salary_cents,
               m.name as manager_name
        FROM employees e
        LEFT JOIN employees m ON e.manager_id = m.id
        WHERE e.is_active = 1
    ''')
    employees = [dict(row) for row in cursor.fetchall()]
    return jsonify(employees)


# --- LEAVE MANAGEMENT ROUTES ---

@app.route('/api/leave', methods=['POST'])
def request_leave():
    data = request.json
    employee_id = data.get('employee_id')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    is_paid = data.get('is_paid', 1)

    if not all([employee_id, start_date_str, end_date_str]):
        return jsonify({"error": "Missing required fields"}), 400

    # BUSINESS LOGIC: Safeguard against short-notice leave
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    days_notice = (start_date - datetime.now()).days

    if days_notice < 7:
        return jsonify({
            "error": "Policy violation: Leave requests require at least 7 days notice to ensure team coverage."
        }), 400

    db = get_db()
    db.execute('''
        INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid)
        VALUES (?, ?, ?, 'pending', ?)
    ''', (employee_id, start_date_str, end_date_str, is_paid))
    db.commit()

    return jsonify({"message": "Leave requested successfully"}), 201


@app.route('/api/leave/<int:request_id>/approve', methods=['POST'])
def approve_leave(request_id):
    db = get_db()
    db.execute("UPDATE leave_requests SET status = 'approved' WHERE id = ?", (request_id,))
    db.commit()
    return jsonify({"message": "Leave approved"})


# --- MATH HELPER ---

def calculate_taxes(gross_cents):
    """
    Simple progressive tax bracket (values in cents).
    Bucket 1 (0 - $1,000): 0%
    Bucket 2 ($1,001 - $3,000): 10%
    Bucket 3 (Above $3,000): 20%
    """
    tax = 0
    remaining = gross_cents

    # Calculate top bucket first
    if remaining > 300000:
        tax += (remaining - 300000) * 0.20
        remaining = 300000

    # Calculate middle bucket
    if remaining > 100000:
        tax += (remaining - 100000) * 0.10

    # Bottom bucket is 0%, so no math needed.
    return int(tax)


# --- PAYROLL ROUTE ---

@app.route('/api/payroll/generate', methods=['POST'])
def generate_payroll():
    data = request.json
    period = data.get('period')  # Expected format: 'YYYY-MM'

    if not period:
        return jsonify({"error": "Period is required (YYYY-MM)"}), 400

    year, month = map(int, period.split('-'))
    _, days_in_month = calendar.monthrange(year, month)

    period_start = datetime(year, month, 1)
    period_end = datetime(year, month, days_in_month)

    db = get_db()

    # Fetch all active employees
    cursor = db.execute("SELECT * FROM employees WHERE is_active = 1")
    employees = cursor.fetchall()

    processed_records = []

    for emp in employees:
        annual_salary = emp['salary_cents']
        monthly_gross = annual_salary // 12
        daily_rate = monthly_gross // days_in_month

        # 1. Pro-ration: Mid-month Joiner
        start_date = datetime.strptime(emp['start_date'], '%Y-%m-%d')
        working_days = days_in_month

        if start_date > period_start:
            if start_date > period_end:
                continue  # Employee hasn't joined yet; skip them.
            working_days = (period_end - start_date).days + 1

        # 2. Pro-ration: Unpaid Leave
        # Fetch approved unpaid leave overlapping this specific month
        leave_cursor = db.execute('''
            SELECT start_date, end_date FROM leave_requests
            WHERE employee_id = ? AND status = 'approved' AND is_paid = 0
            AND (start_date <= ? AND end_date >= ?)
        ''', (emp['id'], period_end.strftime('%Y-%m-%d'), period_start.strftime('%Y-%m-%d')))

        unpaid_leave_days = 0
        for req in leave_cursor.fetchall():
            # Clamp the leave dates to the current month's boundaries
            l_start = max(datetime.strptime(req['start_date'], '%Y-%m-%d'), period_start)
            l_end = min(datetime.strptime(req['end_date'], '%Y-%m-%d'), period_end)
            unpaid_leave_days += (l_end - l_start).days + 1

        actual_working_days = working_days - unpaid_leave_days

        # 3. Calculate Final Pay
        actual_gross = daily_rate * actual_working_days

        tax_deduction = calculate_taxes(actual_gross)
        social_security = int(actual_gross * 0.05)  # Flat 5% SS
        total_deductions = tax_deduction + social_security

        net_pay = actual_gross - total_deductions

        # 4. Save to Database
        db.execute('''
            INSERT INTO payslips (employee_id, period, gross_pay_cents, deductions_cents, net_pay_cents)
            VALUES (?, ?, ?, ?, ?)
        ''', (emp['id'], period, actual_gross, total_deductions, net_pay))

        processed_records.append({
            "employee": emp['name'],
            "gross": actual_gross / 100,  # Convert back to standard currency for the UI
            "net": net_pay / 100
        })

    db.commit()

    return jsonify({
        "message": f"Payroll generated for {period}",
        "records_processed": len(processed_records),
        "summary": processed_records
    }), 201

@app.route('/api/leave', methods=['GET'])
def get_leave_requests():
    db = get_db()
    cursor = db.execute('''
        SELECT l.id, l.start_date, l.end_date, l.status, l.is_paid, e.name as employee_name
        FROM leave_requests l
        JOIN employees e ON l.employee_id = e.id
        ORDER BY l.start_date DESC
    ''')
    return jsonify([dict(row) for row in cursor.fetchall()])

@app.route('/api/payroll', methods=['GET'])
def get_payroll():
    period = request.args.get('period')
    db = get_db()
    cursor = db.execute('''
        SELECT p.period, p.gross_pay_cents, p.deductions_cents, p.net_pay_cents, e.name as employee_name
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.period = ?
    ''', (period,))
    return jsonify([dict(row) for row in cursor.fetchall()])

if __name__ == '__main__':
    app.run(debug=True, port=5000)