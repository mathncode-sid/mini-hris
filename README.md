# Mini-HRIS

A lightweight internal HR and Payroll tool built to solve real-world spreadsheet inefficiencies. This project prioritizes accurate financial math, robust leave request safeguards, and a seamless developer experience over framework complexity.

## Scope & Prioritization

The brief noted a preference for depth in a few modules rather than a shallow complete system. I prioritized **Backend Business Logic, Statutory Compliance, and Data Integrity**.

*   **Flask + Vanilla JS:** I chose vanilla HTML/CSS/JS for the frontend to avoid build steps and state management overhead. This allowed me to dedicate maximum time to the core grading criteria: the financial math, unit tests, and HR safeguards on the backend.
*   **Cents-Based Integer Math:** Floating-point inaccuracies can silently ruin payroll systems. All monetary values are strictly calculated as integers (cents) on the backend, only converting to decimals for the final UI render.
*   **Zero Configuration (SQLite):** Chosen to eliminate reviewer friction. It requires no Docker containers or PostgreSQL credential configuration, ensuring the app runs flawlessly out of the box using the included pre-populated sample database.

## Core Features & Business Rules

### 1. Leave Management: The 7-Day Notice Safeguard
Real-world HR systems run into problems when spreadsheets fail to catch short-notice leave, leaving teams unexpectedly under-covered.
*   **The Rule:** The backend enforces a strict minimum 7-day notice period for all new leave requests.
*   **The Implementation:** If an employee requests leave starting less than 7 days from the current date, the API rejects the payload with a 400 error and surfaces an animated policy violation warning on the frontend.

### 2. Payroll Automation & Statutory Compliance (Kenyan Context)
Payroll generation handles edge cases such as mid-month joiners and unpaid leave by dynamically calculating the exact number of days in the requested month (handling leap years and 31-day months accurately). 

The system implements fully compliant Kenyan statutory deductions:
*   **NSSF:** 6% deduction capped at KES 36,000 (Tier 1 & 2).
*   **PAYE (Income Tax):** A progressive bracket system applied to income *after* NSSF deduction, factoring in the standard KES 2,400 monthly Personal Relief.
    *   10% up to KES 24,000
    *   25% up to KES 32,333
    *   30% up to KES 500,000
    *   32.5% up to KES 800,000
    *   35% above KES 800,000
*   **SHIF & Housing Levy:** Flat rate deductions of 2.75% and 1.5% applied directly to gross pay.

## How to Run Locally

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd mini-hris
   
  

2. **Set up the virtual environment:**
```bash
python -m venv venv
venv\Scripts\activate  # For Windows environments

```


3. **Install dependencies:**
```bash
pip install Flask

```


4. **Initialize the database (Optional):**
```bash
python init_db.py

```


5. **Start the server:**
```bash
python app.py

```


Navigate to `http://127.0.0.1:5000` in your browser.

## Running the Unit Tests

The core business logic is defended by a suite of unit tests isolated on a temporary test database. To verify the PAYE tax math and the 7-day leave notice safeguard, run:

```bash
python -m unittest test_app.py

```

## Future Improvements (Stretch Goals)

Given more time, I would expand the system with the following features:

1. **Role-Based Access Control (RBAC):** Implementing JWT-based authentication to restrict the "Approve" button and Payroll generation strictly to users with a `Manager` or `HR` role.
2. **Concurrency Handling:** Implementing database locking during the payroll generation route to prevent race conditions if multiple admins attempt to generate the same period simultaneously.
3. **Export Capabilities:** A route to generate and download Payslips in PDF format or export a month's payroll ledger as a CSV file.

```
