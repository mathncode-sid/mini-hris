const state = {
    employees: [],
    selectedPeriod: new Date().toISOString().slice(0, 7),
};

const formatMoney = (cents = 0) =>
    `KES ${(cents / 100).toLocaleString('en-KE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;

const formatDate = (dateString) => {
    const [year, month, day] = dateString.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
    });
};

function setText(id, value) {
    document.getElementById(id).textContent = value;
}

function moneyCell(cents, negative = false) {
    const td = document.createElement('td');
    td.textContent = `${negative ? '-' : ''}${formatMoney(cents)}`;
    td.className = negative ? 'money negative' : 'money';
    return td;
}

function emptyRow(colspan, message) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = colspan;
    td.className = 'empty-state';
    td.textContent = message;
    tr.appendChild(td);
    return tr;
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3800);
}

async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || 'Request failed');
    }
    return data;
}

function buildBadge(status, escalated = false) {
    const badge = document.createElement('span');
    badge.className = `badge ${status}${escalated ? ' escalated' : ''}`;
    badge.textContent = escalated && status === 'pending' ? 'escalated' : status;
    return badge;
}

function createCell(text, className = '') {
    const td = document.createElement('td');
    td.textContent = text;
    if (className) td.className = className;
    return td;
}

document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach((nav) => nav.classList.remove('active'));
        document.querySelectorAll('.view').forEach((view) => view.classList.remove('active'));

        button.classList.add('active');
        const target = button.dataset.target;
        document.getElementById(target).classList.add('active');

        if (target === 'dashboard') loadDashboard();
        if (target === 'employees') loadEmployees();
        if (target === 'leave') loadLeaveRequests();
        if (target === 'payroll') loadPayroll(state.selectedPeriod);
    });
});

async function loadEmployees() {
    const tbody = document.getElementById('employees-body');
    tbody.replaceChildren(emptyRow(7, 'Loading employees...'));

    try {
        state.employees = await api('/api/employees');
        populateEmployeeSelect();

        if (state.employees.length === 0) {
            tbody.replaceChildren(emptyRow(7, 'No active employees found.'));
            return;
        }

        const rows = state.employees.map((employee) => {
            const tr = document.createElement('tr');
            const actionCell = document.createElement('td');
            const deactivate = document.createElement('button');
            deactivate.className = 'danger-btn small';
            deactivate.textContent = 'Deactivate';
            deactivate.addEventListener('click', () => deactivateEmployee(employee.id, employee.name));
            actionCell.appendChild(deactivate);

            tr.append(
                createCell(employee.name, 'strong-cell'),
                createCell(employee.role),
                createCell(employee.team),
                createCell(employee.manager_name || 'No manager'),
                createCell(employee.employment_type),
                moneyCell(employee.salary_cents),
                actionCell,
            );
            return tr;
        });
        tbody.replaceChildren(...rows);
    } catch (error) {
        tbody.replaceChildren(emptyRow(7, error.message));
    }
}

async function deactivateEmployee(id, name) {
    const confirmed = window.confirm(`Deactivate ${name}? Payroll history will remain available.`);
    if (!confirmed) return;

    try {
        const data = await api(`/api/employees/${id}/deactivate`, { method: 'POST' });
        showToast(data.message);
        await Promise.all([loadEmployees(), loadDashboard(), loadLeaveRequests()]);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function populateEmployeeSelect() {
    const select = document.getElementById('leave-emp-id');
    const currentValue = select.value;
    select.replaceChildren();

    state.employees.forEach((employee) => {
        const option = document.createElement('option');
        option.value = employee.id;
        option.textContent = `${employee.name} - ${employee.team}`;
        select.appendChild(option);
    });
    if (currentValue) select.value = currentValue;
}

async function loadDashboard() {
    try {
        const data = await api('/api/dashboard');
        setText('metric-employees', data.active_employees);
        setText('metric-pending', data.pending_approvals);
        setText('metric-escalations', data.escalations);

        const outSoon = document.getElementById('out-soon-list');
        if (data.out_soon.length === 0) {
            outSoon.replaceChildren(listEmpty('No approved absences in the next 30 days.'));
        } else {
            outSoon.replaceChildren(...data.out_soon.map((item) => {
                const row = document.createElement('article');
                row.className = 'list-item';
                row.append(
                    stackText(item.name, item.team),
                    stackText(`${formatDate(item.start_date)} - ${formatDate(item.end_date)}`, 'Approved'),
                );
                return row;
            }));
        }

        const balances = document.getElementById('balance-list');
        if (data.leave_balances.length === 0) {
            balances.replaceChildren(listEmpty('No leave balances available.'));
        } else {
            balances.replaceChildren(...data.leave_balances.map((item) => {
                const row = document.createElement('article');
                row.className = 'list-item';
                row.append(
                    stackText(item.employee_name, `${item.used_days} days used`),
                    stackText(`${item.remaining_days}`, 'days left'),
                );
                return row;
            }));
        }
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function stackText(primary, secondary) {
    const wrapper = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = primary;
    const span = document.createElement('span');
    span.textContent = secondary;
    wrapper.append(strong, span);
    return wrapper;
}

function listEmpty(message) {
    const p = document.createElement('p');
    p.className = 'empty-state compact';
    p.textContent = message;
    return p;
}

document.getElementById('new-leave-btn').addEventListener('click', () => {
    document.getElementById('leave-form-container').classList.toggle('hidden');
});

document.getElementById('cancel-leave-btn').addEventListener('click', () => {
    document.getElementById('leave-form').reset();
    document.getElementById('leave-form-container').classList.add('hidden');
});

document.getElementById('leave-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = document.getElementById('submit-leave-btn');
    button.disabled = true;
    button.textContent = 'Submitting...';

    const payload = {
        employee_id: Number(document.getElementById('leave-emp-id').value),
        start_date: document.getElementById('leave-start').value,
        end_date: document.getElementById('leave-end').value,
        is_paid: Number(document.getElementById('leave-paid').value),
        reason: document.getElementById('leave-reason').value,
    };

    try {
        await api('/api/leave', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        showToast('Leave request submitted');
        event.target.reset();
        document.getElementById('leave-form-container').classList.add('hidden');
        await Promise.all([loadLeaveRequests(), loadDashboard()]);
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = 'Submit request';
    }
});

async function loadLeaveRequests() {
    const tbody = document.getElementById('leave-body');
    tbody.replaceChildren(emptyRow(6, 'Loading requests...'));

    try {
        const requests = await api('/api/leave');
        if (requests.length === 0) {
            tbody.replaceChildren(emptyRow(6, 'No leave requests yet.'));
            return;
        }

        const rows = requests.map((requestItem) => {
            const tr = document.createElement('tr');
            const statusCell = document.createElement('td');
            statusCell.appendChild(buildBadge(requestItem.status, Boolean(requestItem.needs_escalation)));

            const actionCell = document.createElement('td');
            if (requestItem.status === 'pending') {
                const actions = document.createElement('div');
                actions.className = 'row-actions';
                const approve = document.createElement('button');
                approve.className = 'secondary-btn small';
                approve.textContent = 'Approve';
                approve.addEventListener('click', () => decideLeave(requestItem.id, 'approve'));
                const reject = document.createElement('button');
                reject.className = 'danger-btn small';
                reject.textContent = 'Reject';
                reject.addEventListener('click', () => decideLeave(requestItem.id, 'reject'));
                actions.append(approve, reject);
                actionCell.appendChild(actions);
            } else {
                actionCell.textContent = requestItem.rejection_reason || '-';
            }

            tr.append(
                createCell(requestItem.employee_name, 'strong-cell'),
                createCell(requestItem.team),
                createCell(`${formatDate(requestItem.start_date)} - ${formatDate(requestItem.end_date)}`),
                createCell(requestItem.is_paid ? 'Paid' : 'Unpaid'),
                statusCell,
                actionCell,
            );
            return tr;
        });
        tbody.replaceChildren(...rows);
    } catch (error) {
        tbody.replaceChildren(emptyRow(6, error.message));
    }
}

async function decideLeave(id, decision) {
    try {
        const body = decision === 'reject'
            ? JSON.stringify({ reason: 'Rejected by manager' })
            : undefined;
        await api(`/api/leave/${id}/${decision}`, {
            method: 'POST',
            headers: decision === 'reject' ? { 'Content-Type': 'application/json' } : undefined,
            body,
        });
        showToast(`Leave ${decision === 'approve' ? 'approved' : 'rejected'}`);
        await Promise.all([loadLeaveRequests(), loadDashboard()]);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

document.getElementById('payroll-period').value = state.selectedPeriod;

document.getElementById('generate-payroll-btn').addEventListener('click', async () => {
    const period = document.getElementById('payroll-period').value;
    const button = document.getElementById('generate-payroll-btn');
    if (!period) {
        showToast('Select a payroll period first', 'error');
        return;
    }

    button.disabled = true;
    button.textContent = 'Generating...';
    try {
        const data = await api('/api/payroll/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period }),
        });
        state.selectedPeriod = period;
        showToast(data.message);
        await loadPayroll(period);
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = 'Generate';
    }
});

document.getElementById('view-payroll-btn').addEventListener('click', () => {
    const period = document.getElementById('payroll-period').value;
    if (!period) {
        showToast('Select a payroll period first', 'error');
        return;
    }
    state.selectedPeriod = period;
    loadPayroll(period);
});

document.getElementById('export-payroll-btn').addEventListener('click', async () => {
    const period = document.getElementById('payroll-period').value;
    if (!period) {
        showToast('Select a payroll period first', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/payroll/export?period=${encodeURIComponent(period)}`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.error || 'Export failed');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `payroll-${period}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        showToast(`Payroll CSV exported for ${period}`);
    } catch (error) {
        showToast(error.message, 'error');
    }
});

async function loadPayroll(period) {
    const tbody = document.getElementById('payroll-body');
    if (!period) {
        tbody.replaceChildren(emptyRow(8, 'No period selected.'));
        return;
    }
    tbody.replaceChildren(emptyRow(8, 'Loading payslips...'));

    try {
        const payslips = await api(`/api/payroll?period=${encodeURIComponent(period)}`);
        if (payslips.length === 0) {
            document.getElementById('payroll-summary').textContent = `No generated payroll for ${period}.`;
            tbody.replaceChildren(emptyRow(8, `No generated payroll for ${period}.`));
            return;
        }

        const totals = payslips.reduce((sum, row) => ({
            gross: sum.gross + row.gross_pay_cents,
            net: sum.net + row.net_pay_cents,
        }), { gross: 0, net: 0 });
        document.getElementById('payroll-summary').textContent =
            `${payslips.length} payslips, ${formatMoney(totals.gross)} gross, ${formatMoney(totals.net)} net`;

        const rows = payslips.map((payslip) => {
            const tr = document.createElement('tr');
            tr.append(
                createCell(payslip.employee_name, 'strong-cell'),
                moneyCell(payslip.gross_pay_cents),
                moneyCell(payslip.nssf_cents, true),
                moneyCell(payslip.paye_cents, true),
                moneyCell(payslip.shif_cents, true),
                moneyCell(payslip.housing_levy_cents, true),
                createCell(String(payslip.unpaid_leave_days)),
                moneyCell(payslip.net_pay_cents),
            );
            return tr;
        });
        tbody.replaceChildren(...rows);
    } catch (error) {
        tbody.replaceChildren(emptyRow(8, error.message));
    }
}

document.getElementById('refresh-dashboard-btn').addEventListener('click', loadDashboard);

loadEmployees().then(() => {
    loadDashboard();
    loadLeaveRequests();
    loadPayroll(state.selectedPeriod);
});
