// --- FORMATTING UTILS ---
const formatMoney = (cents) => `$${(cents / 100).toFixed(2)}`;
const formatDate = (dateString) => new Date(dateString).toLocaleDateString();

// --- NAVIGATION ---
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        
        e.target.classList.add('active');
        const targetId = e.target.getAttribute('data-target');
        document.getElementById(targetId).classList.add('active');

        // Load data based on view
        if(targetId === 'employees') loadEmployees();
        if(targetId === 'leave') loadLeaveRequests();
    });
});

// --- EMPLOYEES ---
async function loadEmployees() {
    const tbody = document.getElementById('employees-body');
    try {
        const res = await fetch('/api/employees');
        const employees = await res.json();
        
        if(employees.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No employees found.</td></tr>`;
            return;
        }

        tbody.innerHTML = employees.map(emp => `
            <tr>
                <td><strong>${emp.name}</strong></td>
                <td>${emp.role}</td>
                <td>${emp.manager_name || 'None'}</td>
                <td>${formatMoney(emp.salary_cents)}</td>
            </tr>
        `).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state" style="color:red">Failed to load data.</td></tr>`;
    }
}

// --- LEAVE MANAGEMENT ---
document.getElementById('new-leave-btn').addEventListener('click', () => {
    document.getElementById('leave-form-container').classList.toggle('hidden');
});

document.getElementById('leave-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submit-leave-btn');
    const errorMsg = document.getElementById('leave-error');
    
    btn.disabled = true;
    btn.innerText = 'Submitting...';
    errorMsg.innerText = '';

    const payload = {
        employee_id: document.getElementById('leave-emp-id').value,
        start_date: document.getElementById('leave-start').value,
        end_date: document.getElementById('leave-end').value,
        is_paid: 1
    };

    const res = await fetch('/api/leave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    btn.disabled = false;
    btn.innerText = 'Submit Request';

    if (!res.ok) {
        errorMsg.innerText = data.error;
    } else {
        document.getElementById('leave-form').reset();
        document.getElementById('leave-form-container').classList.add('hidden');
        loadLeaveRequests();
    }
});

async function loadLeaveRequests() {
    const tbody = document.getElementById('leave-body');
    const res = await fetch('/api/leave');
    const requests = await res.json();

    if(requests.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No leave requests.</td></tr>`;
        return;
    }

    tbody.innerHTML = requests.map(req => `
        <tr>
            <td>${req.employee_name}</td>
            <td>${formatDate(req.start_date)} - ${formatDate(req.end_date)}</td>
            <td><span class="badge ${req.status}">${req.status}</span></td>
            <td>
                ${req.status === 'pending' ? 
                  `<button class="secondary-btn" onclick="approveLeave(${req.id})">Approve</button>` : 
                  '-'}
            </td>
        </tr>
    `).join('');
}

async function approveLeave(id) {
    await fetch(`/api/leave/${id}/approve`, { method: 'POST' });
    loadLeaveRequests();
}

// --- PAYROLL ---
document.getElementById('generate-payroll-btn').addEventListener('click', async () => {
    const period = document.getElementById('payroll-period').value;
    const statusMsg = document.getElementById('payroll-status');
    const btn = document.getElementById('generate-payroll-btn');

    if(!period) return alert('Select a month first');

    btn.disabled = true;
    btn.innerText = 'Processing...';
    statusMsg.innerText = '';

    const res = await fetch('/api/payroll/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period })
    });

    const data = await res.json();
    btn.disabled = false;
    btn.innerText = 'Run Payroll';

    if(res.ok) {
        statusMsg.innerText = data.message;
        loadPayroll(period);
    }
});

document.getElementById('view-payroll-btn').addEventListener('click', () => {
    const period = document.getElementById('payroll-period').value;
    if(period) loadPayroll(period);
});

async function loadPayroll(period) {
    const tbody = document.getElementById('payroll-body');
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Loading...</td></tr>`;
    
    const res = await fetch(`/api/payroll?period=${period}`);
    const payslips = await res.json();

    if(payslips.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No payroll data for ${period}.</td></tr>`;
        return;
    }

    tbody.innerHTML = payslips.map(p => `
        <tr>
            <td><strong>${p.employee_name}</strong></td>
            <td>${formatMoney(p.gross_pay_cents)}</td>
            <td style="color: var(--error)">-${formatMoney(p.deductions_cents)}</td>
            <td style="color: var(--success); font-weight: bold;">${formatMoney(p.net_pay_cents)}</td>
        </tr>
    `).join('');
}

// Init
loadEmployees();