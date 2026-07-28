import os
import sqlite3


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATABASE = os.environ.get('HR_SYSTEM_DATABASE', os.path.join(BASE_DIR, 'hr_system.sqlite'))


def create_schema(conn):
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        team TEXT NOT NULL,
        manager_id INTEGER,
        start_date TEXT NOT NULL,
        salary_cents INTEGER NOT NULL CHECK (salary_cents >= 0),
        employment_type TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (manager_id) REFERENCES employees (id)
    );

    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved', 'rejected')),
        is_paid INTEGER NOT NULL DEFAULT 1,
        reason TEXT DEFAULT '',
        rejection_reason TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT,
        CHECK (end_date >= start_date),
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );

    CREATE TABLE IF NOT EXISTS payslips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        period TEXT NOT NULL,
        gross_pay_cents INTEGER NOT NULL CHECK (gross_pay_cents >= 0),
        deductions_cents INTEGER NOT NULL CHECK (deductions_cents >= 0),
        net_pay_cents INTEGER NOT NULL,
        nssf_cents INTEGER NOT NULL DEFAULT 0,
        paye_cents INTEGER NOT NULL DEFAULT 0,
        shif_cents INTEGER NOT NULL DEFAULT 0,
        housing_levy_cents INTEGER NOT NULL DEFAULT 0,
        taxable_income_cents INTEGER NOT NULL DEFAULT 0,
        unpaid_leave_days INTEGER NOT NULL DEFAULT 0,
        payable_days INTEGER NOT NULL DEFAULT 0,
        generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (employee_id, period),
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );
    ''')


def seed_data(conn):
    conn.executescript('''
        DELETE FROM payslips;
        DELETE FROM leave_requests;
        DELETE FROM employees;

        INSERT INTO employees
            (id, name, role, team, manager_id, start_date, salary_cents, employment_type)
        VALUES
            (1, 'Sarah Mwangi', 'Engineering Manager', 'Engineering', NULL, '2023-01-15', 240000000, 'Full-time'),
            (2, 'David Ochieng', 'Software Engineer', 'Engineering', 1, '2024-02-01', 120000000, 'Full-time'),
            (3, 'Amina Hassan', 'Product Designer', 'Design', 1, '2025-06-10', 150000000, 'Full-time'),
            (4, 'Grace Njeri', 'QA Analyst', 'Engineering', 1, '2026-07-16', 96000000, 'Full-time'),
            (5, 'Joseph Kariuki', 'People Ops Lead', 'People', NULL, '2024-11-01', 180000000, 'Full-time');

        INSERT INTO leave_requests
            (id, employee_id, start_date, end_date, status, is_paid, reason, created_at, decided_at)
        VALUES
            (1, 2, '2026-08-10', '2026-08-14', 'pending', 1, 'Family trip', '2026-07-24 09:00:00', NULL),
            (2, 4, '2026-07-20', '2026-07-22', 'approved', 0, 'Unpaid personal leave', '2026-07-01 10:00:00', '2026-07-02 11:00:00'),
            (3, 3, '2026-08-17', '2026-08-19', 'approved', 1, 'Rest days', '2026-07-25 14:30:00', '2026-07-25 15:00:00');
    ''')
    generate_sample_payroll(conn)


def generate_sample_payroll(conn):
    import calendar
    from datetime import date

    from app import calculate_payslip

    period = '2026-07'
    year, month = 2026, 7
    _, days_in_month = calendar.monthrange(year, month)
    period_start = date(year, month, 1)
    period_end = date(year, month, days_in_month)

    employees = conn.execute('''
        SELECT * FROM employees
        WHERE is_active = 1 AND start_date <= ?
        ORDER BY name
    ''', (period_end.isoformat(),)).fetchall()

    for employee in employees:
        leave_rows = conn.execute('''
            SELECT start_date, end_date FROM leave_requests
            WHERE employee_id = ?
              AND status = 'approved'
              AND is_paid = 0
              AND start_date <= ?
              AND end_date >= ?
        ''', (employee['id'], period_end.isoformat(), period_start.isoformat())).fetchall()
        payslip = calculate_payslip(employee, period_start, period_end, days_in_month, leave_rows)

        conn.execute('''
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


def init_db(path=DEFAULT_DATABASE):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        DROP TABLE IF EXISTS payslips;
        DROP TABLE IF EXISTS leave_requests;
        DROP TABLE IF EXISTS employees;
    ''')
    create_schema(conn)
    seed_data(conn)
    conn.commit()
    conn.close()
    print(f'Database initialized successfully at {path}')


if __name__ == '__main__':
    init_db()
