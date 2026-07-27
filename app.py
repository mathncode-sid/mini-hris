from flask import Flask, request, jsonify, g
import sqlite3
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
DATABASE = 'hr_system.sqlite'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Returns dict-like rows instead of tuples
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)