import unittest
import json
from datetime import datetime, timedelta
import sqlite3

# Import your flask app and the math helper function
import app as myapp 

class HRSystemTestCase(unittest.TestCase):
    def setUp(self):
        # Configure Flask for testing
        myapp.app.testing = True
        self.client = myapp.app.test_client()
        
        # Use a temporary test database so we don't mess up the real one
        myapp.DATABASE = 'test_hr_system.sqlite'
        
        with myapp.app.app_context():
            db = myapp.get_db()
            # Initialize schema for the test environment
            db.executescript('''
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, role TEXT, team TEXT, manager_id INTEGER, 
                    start_date TEXT, salary_cents INTEGER, employment_type TEXT, is_active BOOLEAN DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS leave_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER, start_date TEXT, end_date TEXT, 
                    status TEXT, is_paid BOOLEAN
                );
                DELETE FROM employees;
                DELETE FROM leave_requests;
                
                -- Insert a dummy employee for testing
                INSERT INTO employees (id, name, role, team, start_date, salary_cents, employment_type) 
                VALUES (1, 'Test Employee', 'Tester', 'QA', '2023-01-01', 120000000, 'Full-time');
            ''')
            db.commit()

    # --- TEST 1: KRA PAYE MATH ---
    
    def test_tax_below_personal_relief(self):
        """Test that a gross income of 24,000 KES results in 0 tax due to the 2,400 relief."""
        # 24,000 KES = 2,400,000 cents
        tax = myapp.calculate_taxes(2400000)
        self.assertEqual(tax, 0)

    def test_tax_second_bracket(self):
        """
        Test income of 30,000 KES.
        Tier 1 (First 24k @ 10%): 2,400
        Tier 2 (Next 6k @ 25%): 1,500
        Total: 3,900 - 2,400 (Relief) = 1,500 KES
        """
        # 30,000 KES = 3,000,000 cents
        tax = myapp.calculate_taxes(3000000)
        # Expected tax: 1,500 KES = 150,000 cents
        self.assertEqual(tax, 150000)

    # --- TEST 2: LEAVE REQUEST SAFEGUARDS ---

    def test_leave_request_under_7_days(self):
        """Test that the API rejects leave requested with less than 7 days notice."""
        # Create a date exactly 3 days from right now
        short_notice_date = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        
        response = self.client.post('/api/leave', json={
            "employee_id": 1,
            "start_date": short_notice_date,
            "end_date": short_notice_date,
            "is_paid": 1
        })
        
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Policy violation", data['error'])

    def test_leave_request_valid_notice(self):
        """Test that the API accepts leave requested with more than 7 days notice."""
        # Create a date 14 days in the future
        valid_notice_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        
        response = self.client.post('/api/leave', json={
            "employee_id": 1,
            "start_date": valid_notice_date,
            "end_date": valid_notice_date,
            "is_paid": 1
        })
        
        self.assertEqual(response.status_code, 201)
        self.assertEqual(json.loads(response.data)['message'], "Leave requested successfully")

if __name__ == '__main__':
    unittest.main()