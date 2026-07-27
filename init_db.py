import sqlite3

def init_db():
    conn = sqlite3.connect('hr_system.sqlite')
    cursor = conn.cursor()

    # 1. Employees Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        team TEXT NOT NULL,
        manager_id INTEGER,
        start_date TEXT NOT NULL, -- Format: YYYY-MM-DD
        salary_cents INTEGER NOT NULL, -- Store in cents to avoid float errors
        employment_type TEXT NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        FOREIGN KEY (manager_id) REFERENCES employees (id)
    )
    ''')

    # 2. Leave Requests Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        is_paid BOOLEAN DEFAULT 1, -- To calculate pro-rated payroll later
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    )
    ''')

    # 3. Payslips Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payslips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        period TEXT NOT NULL, -- Format: YYYY-MM
        gross_pay_cents INTEGER NOT NULL,
        deductions_cents INTEGER NOT NULL,
        net_pay_cents INTEGER NOT NULL,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    )
    ''')

    # Clear existing data so running this script multiple times doesn't create duplicates
    cursor.executescript('''
        DELETE FROM payslips;
        DELETE FROM leave_requests;
        DELETE FROM employees;
    ''')

    # Insert Sample Data (Kenyan Context)
    # Note: salary_cents = Annual Salary in KES * 100
    cursor.executescript('''
        -- 1. Manager: KES 2,400,000 annual (KES 200,000/month)
        INSERT INTO employees (id, name, role, team, manager_id, start_date, salary_cents, employment_type) 
        VALUES (1, 'Sarah Mwangi', 'Engineering Manager', 'Engineering', NULL, '2023-01-15', 240000000, 'Full-time');
        
        -- 2. Engineer: KES 1,200,000 annual (KES 100,000/month)
        INSERT INTO employees (id, name, role, team, manager_id, start_date, salary_cents, employment_type) 
        VALUES (2, 'David Ochieng', 'Software Engineer', 'Engineering', 1, '2024-02-01', 120000000, 'Full-time');
        
        -- 3. Designer: KES 1,500,000 annual (KES 125,000/month)
        INSERT INTO employees (id, name, role, team, manager_id, start_date, salary_cents, employment_type) 
        VALUES (3, 'Amina Hassan', 'Product Designer', 'Design', 1, '2025-06-10', 150000000, 'Full-time');

        -- Insert a sample leave request for David
        INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid)
        VALUES (2, '2026-08-10', '2026-08-14', 'pending', 1);
    ''')

    conn.commit()
    conn.close()
    print("Database initialized successfully at hr_system.sqlite")

if __name__ == '__main__':
    init_db()