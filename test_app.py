import os
import sqlite3
import unittest
from datetime import date, timedelta

import app as myapp
from init_db import create_schema


TEST_DB = 'test_hr_system.sqlite'


class HRSystemTestCase(unittest.TestCase):
    def setUp(self):
        myapp.app.testing = True
        myapp.DATABASE = TEST_DB
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

        self.client = myapp.app.test_client()
        with myapp.app.app_context():
            db = myapp.get_db()
            create_schema(db)
            db.executescript('''
                INSERT INTO employees
                    (id, name, role, team, manager_id, start_date, salary_cents, employment_type, is_active)
                VALUES
                    (1, 'Test Manager', 'Manager', 'QA', NULL, '2023-01-01', 120000000, 'Full-time', 1),
                    (2, 'Test Analyst', 'Analyst', 'QA', 1, '2023-01-01', 96000000, 'Full-time', 1),
                    (3, 'Mid Month Hire', 'Engineer', 'Engineering', NULL, '2026-07-16', 120000000, 'Full-time', 1),
                    (4, 'Inactive Person', 'Former', 'QA', 1, '2023-01-01', 120000000, 'Full-time', 0);
            ''')
            db.commit()

    def tearDown(self):
        with myapp.app.app_context():
            db = getattr(myapp.g, '_database', None)
            if db is not None:
                db.close()
                myapp.g._database = None
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def future_date(self, days=14):
        return date.today() + timedelta(days=days)

    def test_tax_below_personal_relief(self):
        self.assertEqual(myapp.calculate_taxes(2400000), 0)

    def test_tax_second_bracket_boundary(self):
        self.assertEqual(myapp.calculate_taxes(3000000), 150000)

    def test_leave_request_under_7_days_is_rejected(self):
        short_notice = self.future_date(3).isoformat()
        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': short_notice,
            'end_date': short_notice,
            'is_paid': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Policy violation', response.get_json()['error'])

    def test_leave_request_valid_notice_is_created(self):
        valid_start = self.future_date(14)
        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': valid_start.isoformat(),
            'end_date': (valid_start + timedelta(days=1)).isoformat(),
            'is_paid': 1,
            'reason': 'Planned break',
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['message'], 'Leave requested successfully')

    def test_leave_request_rejects_invalid_date_order(self):
        valid_start = self.future_date(14)
        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': valid_start.isoformat(),
            'end_date': (valid_start - timedelta(days=1)).isoformat(),
            'is_paid': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('End date', response.get_json()['error'])

    def test_leave_request_rejects_overlap(self):
        valid_start = self.future_date(14)
        with myapp.app.app_context():
            db = myapp.get_db()
            db.execute('''
                INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid)
                VALUES (1, ?, ?, 'approved', 1)
            ''', (valid_start.isoformat(), (valid_start + timedelta(days=2)).isoformat()))
            db.commit()

        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': (valid_start + timedelta(days=1)).isoformat(),
            'end_date': (valid_start + timedelta(days=3)).isoformat(),
            'is_paid': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('overlaps', response.get_json()['error'])

    def test_leave_request_rejects_balance_overage(self):
        valid_start = self.future_date(14)
        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': valid_start.isoformat(),
            'end_date': (valid_start + timedelta(days=20)).isoformat(),
            'is_paid': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('balance', response.get_json()['error'])

    def test_leave_request_rejects_team_under_coverage(self):
        valid_start = self.future_date(14)
        with myapp.app.app_context():
            db = myapp.get_db()
            db.execute('''
                INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid)
                VALUES (2, ?, ?, 'approved', 1)
            ''', (valid_start.isoformat(), valid_start.isoformat()))
            db.commit()

        response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': valid_start.isoformat(),
            'end_date': valid_start.isoformat(),
            'is_paid': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Coverage violation', response.get_json()['error'])

    def test_reject_route_marks_pending_leave_rejected(self):
        valid_start = self.future_date(14)
        create_response = self.client.post('/api/leave', json={
            'employee_id': 1,
            'start_date': valid_start.isoformat(),
            'end_date': valid_start.isoformat(),
            'is_paid': 1,
        })
        self.assertEqual(create_response.status_code, 201)

        response = self.client.post('/api/leave/1/reject', json={'reason': 'Coverage changed'})
        self.assertEqual(response.status_code, 200)

        with myapp.app.app_context():
            status = myapp.get_db().execute('SELECT status FROM leave_requests WHERE id = 1').fetchone()['status']
        self.assertEqual(status, 'rejected')

    def test_payroll_is_idempotent_and_prorates_mid_month_unpaid_leave(self):
        with myapp.app.app_context():
            db = myapp.get_db()
            db.execute('''
                INSERT INTO leave_requests (employee_id, start_date, end_date, status, is_paid)
                VALUES (3, '2026-07-20', '2026-07-22', 'approved', 0)
            ''')
            db.commit()

        first = self.client.post('/api/payroll/generate', json={'period': '2026-07'})
        second = self.client.post('/api/payroll/generate', json={'period': '2026-07'})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        with myapp.app.app_context():
            db = myapp.get_db()
            count = db.execute('''
                SELECT COUNT(*) AS total FROM payslips
                WHERE employee_id = 3 AND period = '2026-07'
            ''').fetchone()['total']
            payslip = db.execute('''
                SELECT * FROM payslips
                WHERE employee_id = 3 AND period = '2026-07'
            ''').fetchone()

        self.assertEqual(count, 1)
        self.assertEqual(payslip['payable_days'], 16)
        self.assertEqual(payslip['unpaid_leave_days'], 3)
        self.assertEqual(payslip['gross_pay_cents'], (10000000 // 31) * 13)

    def test_employee_deactivation_preserves_payslip_history(self):
        self.client.post('/api/payroll/generate', json={'period': '2026-07'})

        response = self.client.post('/api/employees/3/deactivate')
        self.assertEqual(response.status_code, 200)

        employees = self.client.get('/api/employees').get_json()
        self.assertNotIn(3, [employee['id'] for employee in employees])

        payroll = self.client.get('/api/payroll?period=2026-07').get_json()
        self.assertIn('Mid Month Hire', [row['employee_name'] for row in payroll])

    def test_manager_with_active_reports_cannot_be_deactivated(self):
        response = self.client.post('/api/employees/1/deactivate')
        self.assertEqual(response.status_code, 400)
        self.assertIn('direct reports', response.get_json()['error'])

    def test_payroll_csv_export_contains_generated_payslips(self):
        self.client.post('/api/payroll/generate', json={'period': '2026-07'})

        response = self.client.get('/api/payroll/export?period=2026-07')
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/csv')
        self.assertIn('attachment; filename="payroll-2026-07.csv"', response.headers['Content-Disposition'])
        self.assertIn('employee_name', body)
        self.assertIn('Mid Month Hire', body)

    def test_payroll_csv_export_returns_404_for_missing_period(self):
        response = self.client.get('/api/payroll/export?period=2026-08')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
