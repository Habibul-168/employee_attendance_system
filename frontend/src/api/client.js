// All API calls go through this file.
// The base URL is read from the .env file so it's easy to change.
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Generic fetch wrapper — throws an Error with a readable message on failure
async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') {
        // Simple string error from our own HTTPException
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // Pydantic validation error — each item has loc + msg
        detail = body.detail
          .map(e => {
            const field = e.loc ? e.loc.slice(1).join(' → ') : '';
            return field ? `${field}: ${e.msg}` : e.msg;
          })
          .join('\n');
      } else {
        detail = JSON.stringify(body);
      }
    } catch (_) {}
    throw new Error(detail);
  }

  // 204 No Content has no body
  if (res.status === 204) return null;
  return res.json();
}

// ── Employees ──────────────────────────────────────────────────────────────
export function getEmployees(params = {}) {
  const q = new URLSearchParams();
  if (params.department) q.set('department', params.department);
  if (params.page)       q.set('page', params.page);
  if (params.page_size)  q.set('page_size', params.page_size);
  return request(`/employees?${q}`);
}

export function createEmployee(data) {
  return request('/employees', { method: 'POST', body: JSON.stringify(data) });
}

// ── Attendance ──────────────────────────────────────────────────────────────
export function punchIn(data) {
  return request('/attendance/punch-in', { method: 'POST', body: JSON.stringify(data) });
}

export function punchOut(data) {
  return request('/attendance/punch-out', { method: 'POST', body: JSON.stringify(data) });
}

export function getAttendance(params = {}) {
  const q = new URLSearchParams();
  if (params.emp_code)  q.set('emp_code', params.emp_code);
  if (params.date_from) q.set('date_from', params.date_from);
  if (params.date_to)   q.set('date_to', params.date_to);
  if (params.status)    q.set('status', params.status);
  if (params.page)      q.set('page', params.page);
  if (params.page_size) q.set('page_size', params.page_size);
  return request(`/attendance?${q}`);
}

export function regularizeAttendance(emp_code, date, data) {
  return request(`/attendance/${emp_code}/${date}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// ── Analytics ───────────────────────────────────────────────────────────────
export function getEmployeeMonthly(emp_code, month) {
  return request(`/analytics/employees/${emp_code}/monthly?month=${month}`);
}

export function getDepartmentSummary(month, department = '') {
  const q = new URLSearchParams({ month });
  if (department) q.set('department', department);
  return request(`/analytics/departments/summary?${q}`);
}

export function getLateLeaderboard(month, limit = 10, department = '') {
  const q = new URLSearchParams({ month, limit });
  if (department) q.set('department', department);
  return request(`/analytics/leaderboard/late?${q}`);
}

export function getDepartmentTrend(department, from, to) {
  const q = new URLSearchParams({ from, to });
  return request(`/analytics/departments/${department}/trend?${q}`);
}

// ── Health ───────────────────────────────────────────────────────────────────
export function getHealth() {
  return request('/health');
}
