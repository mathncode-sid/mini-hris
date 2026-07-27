// --- FORMATTING UTILS ---
const formatMoney = (cents) => `KES ${(cents / 100).toLocaleString('en-KE', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const formatDate = (dateString) => new Date(dateString).toLocaleDateString();

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerText = message;
    
    container.appendChild(toast);
    
    // Automatically remove the toast from the DOM after the CSS fadeOut animation finishes
    setTimeout(() => {
        toast.remove();
    }, 3800); 
}

// --- NAVIGATION ---
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        
        // Use closest() to ensure clicking the SVG inside the button doesn't break the target
        const targetBtn = e.target.closest('.nav-btn');
        targetBtn.classList.add('active');
        
        const targetId = targetBtn.getAttribute('data-target');
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
    
    btn.disabled = true;
    btn.innerText = 'Submitting...';

    const payload = {
        employee_id: document.getElementById('leave-emp-id').value,
        start_date: document.getElementById('leave-start').value,
        end_date: document.getElementById('leave-end').value,
        is_paid: 1
    };

    try {
        const res = await fetch('/api/leave', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        btn.disabled = false;
        btn.innerText = 'Submit Request';

        if (!res.ok) {
            showToast(data.error || 'Failed to submit request', 'error');
        } else {
            showToast('Leave request submitted successfully', 'success');
            document.getElementById('leave-form').reset();
            document.getElementById('leave-form-container').classList.add('hidden');
            loadLeaveRequests();
        }
    } catch (err) {
        btn.disabled = false;
        btn.innerText = 'Submit Request';
        showToast('A network error occurred', 'error');
    }
});

async function loadLeaveRequests() {
    const tbody = document.getElementById('leave-body');
    try {
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
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state" style="color:red">Failed to load data.</td></tr>`;
    }
}

async function approveLeave(id) {
    try {
        const res = await fetch(`/api/leave/${id}/approve`, { method: 'POST' });
        if(res.ok) {
            showToast('Leave approved successfully', 'success');
            loadLeaveRequests();
        } else {
            showToast('Failed to approve leave', 'error');
        }
    } catch (err) {
        showToast('A network error occurred', 'error');
    }
}

// --- PAYROLL ---
document.getElementById('generate-payroll-btn').addEventListener('click', async () => {
    const period = document.getElementById('payroll-period').value;
    const btn = document.getElementById('generate-payroll-btn');

    if(!period) {
        showToast('Please select a month first', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerText = 'Processing...';

    try {
        const res = await fetch('/api/payroll/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period })
        });

        const data = await res.json();
        btn.disabled = false;
        btn.innerText = 'Run Payroll';

        if(res.ok) {
            showToast(data.message, 'success');
            loadPayroll(period);
        } else {
            showToast(data.error || 'Failed to generate payroll', 'error');
        }
    } catch (err) {
        btn.disabled = false;
        btn.innerText = 'Run Payroll';
        showToast('A network error occurred', 'error');
    }
});

document.getElementById('view-payroll-btn').addEventListener('click', () => {
    const period = document.getElementById('payroll-period').value;
    if(period) {
        loadPayroll(period);
    } else {
        showToast('Please select a month first to view existing payroll', 'error');
    }
});

async function loadPayroll(period) {
    const tbody = document.getElementById('payroll-body');
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Loading...</td></tr>`;
    
    try {
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
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state" style="color:red">Failed to load data.</td></tr>`;
    }
}

// Init
loadEmployees();