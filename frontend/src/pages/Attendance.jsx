import { useEffect, useState } from 'react';
import { punchIn, punchOut, getAttendance } from '../api/client';
import Pagination from '../components/Pagination';
import StatusBadge from '../components/StatusBadge';

function fmtMs(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
}

const FILTER_STATUSES = ['', 'PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'];
const PUNCH_IN_STATUSES = ['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'];

// ABSENT and LEAVE don't have punch times — no punch-out needed
const NO_PUNCH_STATUSES = ['ABSENT', 'LEAVE'];

export default function Attendance() {
  const [piEmp, setPiEmp]         = useState('');
  const [piStatus, setPiStatus]   = useState('PRESENT');
  const [piMsg, setPiMsg]         = useState('');
  const [piErr, setPiErr]         = useState('');
  const [piLoading, setPiLoading] = useState(false);

  const [poEmp, setPoEmp]         = useState('');
  const [poMsg, setPoMsg]         = useState('');
  const [poErr, setPoErr]         = useState('');
  const [poLoading, setPoLoading] = useState(false);

  const [items, setItems]         = useState([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [filters, setFilters]     = useState({ emp_code: '', date_from: '', date_to: '', status: '' });
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError]     = useState('');

  const PAGE_SIZE = 20;
  const isNoPunch = NO_PUNCH_STATUSES.includes(piStatus);

  function loadList(p = 1, f = filters) {
    setListLoading(true);
    setListError('');
    const params = { page: p, page_size: PAGE_SIZE };
    if (f.emp_code)  params.emp_code  = f.emp_code;
    if (f.date_from) params.date_from = f.date_from;
    if (f.date_to)   params.date_to   = f.date_to;
    if (f.status)    params.status    = f.status;
    getAttendance(params)
      .then(d => { setItems(d.items); setTotal(d.total); })
      .catch(e => setListError(e.message))
      .finally(() => setListLoading(false));
  }

  useEffect(() => { loadList(1, filters); }, []);

  function handleFilter(e) {
    const updated = { ...filters, [e.target.name]: e.target.value };
    setFilters(updated);
    setPage(1);
    loadList(1, updated);
  }

  function handlePage(p) { setPage(p); loadList(p, filters); }

  async function handlePunchIn(e) {
    e.preventDefault();
    setPiErr(''); setPiMsg(''); setPiLoading(true);
    try {
      const res = await punchIn({ emp_code: piEmp, status: piStatus });
      setPiMsg(`Recorded: ${res.emp_code} — ${res.date} (${res.status})`);
      setPiEmp('');
      loadList(1, filters);
    } catch (err) {
      setPiErr(err.message);
    } finally {
      setPiLoading(false);
    }
  }

  async function handlePunchOut(e) {
    e.preventDefault();
    setPoErr(''); setPoMsg(''); setPoLoading(true);
    try {
      const res = await punchOut({ emp_code: poEmp });
      setPoMsg(`Punched out: ${res.emp_code} — ${res.work_hours}h worked`);
      setPoEmp('');
      loadList(1, filters);
    } catch (err) {
      setPoErr(err.message);
    } finally {
      setPoLoading(false);
    }
  }

  return (
    <div>
      <h2>Attendance</h2>

      <div className="punch-row">
        {/* Punch In / Mark Attendance */}
        <form className="form-card" onSubmit={handlePunchIn}>
          <h3>Mark Attendance</h3>
          {piErr && <p className="error">{piErr}</p>}
          {piMsg && <p className="success">{piMsg}</p>}
          <label>Emp Code
            <input value={piEmp} onChange={e => setPiEmp(e.target.value)} placeholder="EMP0001" required />
          </label>
          <label>Status
            <select value={piStatus} onChange={e => setPiStatus(e.target.value)}>
              {PUNCH_IN_STATUSES.map(s => <option key={s}>{s}</option>)}
            </select>
          </label>
          {isNoPunch && (
            <p className="field-hint" style={{ color: '#f59e0b', fontWeight: 500, marginBottom: 8 }}>
              ⚠ {piStatus} will be recorded for today with no punch times.
            </p>
          )}
          <button type="submit" disabled={piLoading}>
            {piLoading ? 'Saving…' : isNoPunch ? `Mark as ${piStatus}` : 'Punch In'}
          </button>
        </form>

        {/* Punch Out — only relevant for PRESENT / WFH / ON_DUTY */}
        <form className="form-card" onSubmit={handlePunchOut}>
          <h3>Punch Out</h3>
          {poErr && <p className="error">{poErr}</p>}
          {poMsg && <p className="success">{poMsg}</p>}
          <label>Emp Code
            <input value={poEmp} onChange={e => setPoEmp(e.target.value)} placeholder="EMP0001" required />
          </label>
          <p className="field-hint" style={{ marginBottom: 8 }}>
            Only for PRESENT, WFH, or ON_DUTY records.
          </p>
          <button type="submit" disabled={poLoading}>{poLoading ? 'Saving…' : 'Punch Out'}</button>
        </form>
      </div>

      {/* Filters */}
      <div className="filter-bar" style={{ flexWrap: 'wrap', gap: '8px' }}>
        <input name="emp_code"  placeholder="Emp Code"  value={filters.emp_code}  onChange={handleFilter} />
        <input name="date_from" type="date" value={filters.date_from} onChange={handleFilter} />
        <input name="date_to"   type="date" value={filters.date_to}   onChange={handleFilter} />
        <select name="status" value={filters.status} onChange={handleFilter}>
          {FILTER_STATUSES.map(s => <option key={s} value={s}>{s || 'All Statuses'}</option>)}
        </select>
        <span className="total-label">{total} record{total !== 1 ? 's' : ''}</span>
      </div>

      {listError   && <p className="error">{listError}</p>}
      {listLoading && <p className="loading">Loading…</p>}
      {!listLoading && items.length === 0 && <p className="empty">No attendance records found.</p>}

      {!listLoading && items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Emp Code</th><th>Date</th><th>Status</th>
              <th>Punch In (IST)</th><th>Punch Out (IST)</th>
              <th>Work Hrs</th><th>Late Mins</th><th>OT Mins</th><th>Half Day</th>
            </tr>
          </thead>
          <tbody>
            {items.map(r => (
              <tr key={`${r.emp_code}-${r.date}`}>
                <td><code>{r.emp_code}</code></td>
                <td>{r.date}</td>
                <td><StatusBadge status={r.status} /></td>
                <td>{fmtMs(r.punch_in)}</td>
                <td>{fmtMs(r.punch_out)}</td>
                <td>{r.work_hours ?? '—'}</td>
                <td>{r.late_minutes}</td>
                <td>{r.overtime_minutes}</td>
                <td>{r.half_day ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} total={total} pageSize={PAGE_SIZE} onPage={handlePage} />
    </div>
  );
}
