import { useState } from 'react';
import {
  getEmployeeMonthly,
  getDepartmentSummary,
  getLateLeaderboard,
  getDepartmentTrend,
} from '../api/client';

function currentMonth() { return new Date().toISOString().slice(0, 7); }
function daysAgo(n) {
  const d = new Date(); d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

// Simple CSS bar chart for trend data
function TrendBar({ value, max }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: `${pct}%`, minWidth: 2, height: 14, background: '#3b82f6', borderRadius: 3 }} />
      <span style={{ fontSize: '0.8rem' }}>{(value * 100).toFixed(1)}%</span>
    </div>
  );
}

// ── Tab: Employee Monthly ────────────────────────────────────────────────────
function EmployeeMonthly() {
  const [empCode, setEmpCode] = useState('');
  const [month, setMonth]     = useState(currentMonth());
  const [data, setData]       = useState(null);
  const [err, setErr]         = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setErr(''); setData(null); setLoading(true);
    try { setData(await getEmployeeMonthly(empCode, month)); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div>
      <form className="inline-form" onSubmit={handleSubmit}>
        <input value={empCode} onChange={e => setEmpCode(e.target.value)} placeholder="Emp Code e.g. EMP0001" required />
        <input type="month" value={month} onChange={e => setMonth(e.target.value)} required />
        <button type="submit" disabled={loading}>{loading ? 'Loading…' : 'Get Summary'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      {data && (
        <div className="stat-grid">
          {[
            ['Employee',          data.emp_code],
            ['Month',             data.month],
            ['Working Days',      data.working_days],
            ['Present Days',      data.present_days],
            ['Leave Days',        data.leave_days],
            ['Late Count',        data.late_count],
            ['Total Late Mins',   data.total_late_minutes],
            ['Total OT Mins',     data.total_overtime_minutes],
            ['Attendance %',      data.attendance_pct != null ? `${data.attendance_pct}%` : '—'],
          ].map(([label, val]) => (
            <div key={label} className="stat-item">
              <div className="stat-label">{label}</div>
              <div className="stat-value">{val}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Tab: Department Summary ──────────────────────────────────────────────────
function DeptSummary() {
  const [month, setMonth]   = useState(currentMonth());
  const [dept, setDept]     = useState('');
  const [data, setData]     = useState(null);
  const [err, setErr]       = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setErr(''); setData(null); setLoading(true);
    try { setData(await getDepartmentSummary(month, dept)); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div>
      <form className="inline-form" onSubmit={handleSubmit}>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)} required />
        <input value={dept} onChange={e => setDept(e.target.value)} placeholder="Department (optional)" />
        <button type="submit" disabled={loading}>{loading ? 'Loading…' : 'Get Summary'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      {data && data.items.length === 0 && <p className="empty">No data for this selection.</p>}
      {data && data.items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Department</th><th>Headcount</th><th>Present Days</th>
              <th>Avg Work Hrs</th><th>Late Count</th><th>Leave Count</th><th>On Duty</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(d => (
              <tr key={d.department}>
                <td>{d.department}</td>
                <td>{d.headcount}</td>
                <td>{d.present_days}</td>
                <td>{d.avg_work_hours ?? '—'}</td>
                <td>{d.late_count}</td>
                <td>{d.leave_count}</td>
                <td>{d.on_duty_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Tab: Late Leaderboard ────────────────────────────────────────────────────
function LateLeaderboard() {
  const [month, setMonth]   = useState(currentMonth());
  const [dept, setDept]     = useState('');
  const [limit, setLimit]   = useState(10);
  const [data, setData]     = useState(null);
  const [err, setErr]       = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setErr(''); setData(null); setLoading(true);
    try { setData(await getLateLeaderboard(month, limit, dept)); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div>
      <form className="inline-form" onSubmit={handleSubmit}>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)} required />
        <input value={dept} onChange={e => setDept(e.target.value)} placeholder="Department (optional)" />
        <input type="number" value={limit} min={1} max={50} onChange={e => setLimit(Number(e.target.value))} style={{ width: 70 }} />
        <button type="submit" disabled={loading}>{loading ? 'Loading…' : 'Get Leaderboard'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      {data && data.items.length === 0 && <p className="empty">No late arrivals for this selection.</p>}
      {data && data.items.length > 0 && (
        <table>
          <thead>
            <tr><th>Rank</th><th>Emp Code</th><th>Name</th><th>Department</th><th>Late Days</th><th>Total Late Mins</th></tr>
          </thead>
          <tbody>
            {data.items.map(r => (
              <tr key={r.emp_code}>
                <td>#{r.rank}</td>
                <td><code>{r.emp_code}</code></td>
                <td>{r.name}</td>
                <td>{r.department}</td>
                <td>{r.late_count}</td>
                <td>{r.total_late_minutes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Tab: Department Trend ────────────────────────────────────────────────────
function DeptTrend() {
  const [dept, setDept]     = useState('');
  const [from, setFrom]     = useState(daysAgo(30));
  const [to, setTo]         = useState(daysAgo(0));
  const [data, setData]     = useState(null);
  const [err, setErr]       = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setErr(''); setData(null); setLoading(true);
    try { setData(await getDepartmentTrend(dept, from, to)); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  const maxRate = data ? Math.max(...data.items.map(r => r.attendance_rate ?? 0), 0.001) : 1;

  return (
    <div>
      <form className="inline-form" onSubmit={handleSubmit}>
        <input value={dept} onChange={e => setDept(e.target.value)} placeholder="Department e.g. Engineering" required />
        <input type="date" value={from} onChange={e => setFrom(e.target.value)} required />
        <input type="date" value={to}   onChange={e => setTo(e.target.value)}   required />
        <button type="submit" disabled={loading}>{loading ? 'Loading…' : 'Get Trend'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      {data && data.items.length === 0 && <p className="empty">No trend data for this selection.</p>}
      {data && data.items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Date</th><th>Working Day</th><th>Headcount</th>
              <th>Present</th><th>Late</th><th>Attendance Rate</th><th>7-Day Avg</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(r => (
              <tr key={r.date}>
                <td>{r.date}</td>
                <td>{r.is_working_day ? 'Yes' : 'No'}</td>
                <td>{r.headcount}</td>
                <td>{r.present_count}</td>
                <td>{r.late_count}</td>
                <td>
                  {r.attendance_rate != null
                    ? <TrendBar value={r.attendance_rate} max={maxRate} />
                    : '—'}
                </td>
                <td>{r.moving_avg_7d != null ? `${(r.moving_avg_7d * 100).toFixed(1)}%` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Main Analytics page with tabs ────────────────────────────────────────────
const TABS = [
  { id: 'monthly',     label: 'Employee Monthly',     Component: EmployeeMonthly },
  { id: 'dept',        label: 'Department Summary',   Component: DeptSummary },
  { id: 'leaderboard', label: 'Late Leaderboard',     Component: LateLeaderboard },
  { id: 'trend',       label: 'Department Trend',     Component: DeptTrend },
];

export default function Analytics() {
  const [activeTab, setActiveTab] = useState('monthly');
  const { Component } = TABS.find(t => t.id === activeTab);

  return (
    <div>
      <h2>Analytics</h2>
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab-btn${activeTab === t.id ? ' active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="tab-content">
        <Component />
      </div>
    </div>
  );
}
