import { useEffect, useState } from 'react';
import { getEmployees, getDepartmentSummary, getLateLeaderboard, getHealth } from '../api/client';
import StatusBadge from '../components/StatusBadge';

// Returns current month as "YYYY-MM"
function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

export default function Dashboard() {
  const month = currentMonth();
  const [health, setHealth]       = useState(null);
  const [empTotal, setEmpTotal]   = useState(null);
  const [deptSummary, setDeptSummary] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [error, setError]         = useState('');
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getHealth(),
      getEmployees({ page_size: 1 }),
      getDepartmentSummary(month),
      getLateLeaderboard(month, 5),
    ])
      .then(([h, emp, dept, late]) => {
        setHealth(h);
        setEmpTotal(emp.total);
        setDeptSummary(dept.items || []);
        setLeaderboard(late.items || []);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [month]);

  if (loading) return <p className="loading">Loading dashboard…</p>;

  return (
    <div>
      <h2>Dashboard — {month}</h2>
      {error && <p className="error">{error}</p>}

      {/* Summary cards */}
      <div className="cards">
        <div className="card">
          <div className="card-label">DB Status</div>
          <div className="card-value" style={{ color: health?.status === 'ok' ? '#22c55e' : '#ef4444' }}>
            {health?.status === 'ok' ? '● Online' : '● Offline'}
          </div>
        </div>
        <div className="card">
          <div className="card-label">Total Employees</div>
          <div className="card-value">{empTotal ?? '—'}</div>
        </div>
        <div className="card">
          <div className="card-label">Departments</div>
          <div className="card-value">{deptSummary.length}</div>
        </div>
        <div className="card">
          <div className="card-label">Late Arrivals This Month</div>
          <div className="card-value">
            {leaderboard.reduce((s, r) => s + r.late_count, 0)}
          </div>
        </div>
      </div>

      {/* Department summary table */}
      <h3>Department Summary</h3>
      {deptSummary.length === 0 ? (
        <p className="empty">No department data for {month}.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Department</th>
              <th>Headcount</th>
              <th>Present Days</th>
              <th>Avg Work Hours</th>
              <th>Late Count</th>
              <th>Leave Count</th>
            </tr>
          </thead>
          <tbody>
            {deptSummary.map(d => (
              <tr key={d.department}>
                <td>{d.department}</td>
                <td>{d.headcount}</td>
                <td>{d.present_days}</td>
                <td>{d.avg_work_hours ?? '—'}</td>
                <td>{d.late_count}</td>
                <td>{d.leave_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Late leaderboard */}
      <h3>Top Late Arrivals This Month</h3>
      {leaderboard.length === 0 ? (
        <p className="empty">No late arrivals recorded for {month}.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Employee</th>
              <th>Department</th>
              <th>Late Days</th>
              <th>Total Late Mins</th>
            </tr>
          </thead>
          <tbody>
            {leaderboard.map(r => (
              <tr key={r.emp_code}>
                <td>#{r.rank}</td>
                <td>{r.name} ({r.emp_code})</td>
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
