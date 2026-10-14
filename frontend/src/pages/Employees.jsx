import { useEffect, useState } from 'react';
import { getEmployees, createEmployee } from '../api/client';
import Pagination from '../components/Pagination';

const EMPTY_FORM = {
  emp_code: '', name: '', email: '', department: '',
  shift_start: '09:30', shift_end: '18:30', joined_on: '',
};

export default function Employees() {
  const [items, setItems]         = useState([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [deptFilter, setDeptFilter] = useState('');
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');

  const [showForm, setShowForm]   = useState(false);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const PAGE_SIZE = 20;

  function load(p = page, dept = deptFilter) {
    setLoading(true);
    setError('');
    getEmployees({ page: p, page_size: PAGE_SIZE, department: dept || undefined })
      .then(data => { setItems(data.items); setTotal(data.total); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(1, deptFilter); setPage(1); }, [deptFilter]);

  function handlePage(p) { setPage(p); load(p, deptFilter); }

  function handleFormChange(e) {
    setForm(f => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    setSubmitting(true);
    try {
      await createEmployee(form);
      setFormSuccess(`Employee ${form.emp_code} created successfully.`);
      setForm(EMPTY_FORM);
      load(1, deptFilter);
      setPage(1);
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>Employees</h2>
        <button onClick={() => { setShowForm(f => !f); setFormError(''); setFormSuccess(''); }}>
          {showForm ? 'Cancel' : '+ Add Employee'}
        </button>
      </div>

      {/* Add employee form */}
      {showForm && (
        <form className="form-card" onSubmit={handleSubmit}>
          <h3>New Employee</h3>
          {formError   && <p className="error">{formError}</p>}
          {formSuccess && <p className="success">{formSuccess}</p>}
          <div className="form-grid">
            <label>
              Emp Code
              <input
                name="emp_code"
                value={form.emp_code}
                onChange={handleFormChange}
                placeholder="EMP0001"
                pattern="^EMP\d{4,6}$"
                title="Format: EMP followed by 4–6 digits, e.g. EMP0001"
                required
              />
              <span className="field-hint">Format: EMP0001 – EMP999999</span>
            </label>
            <label>Name<input name="name" value={form.name} onChange={handleFormChange} placeholder="Full name" required /></label>
            <label>Email<input name="email" type="email" value={form.email} onChange={handleFormChange} placeholder="user@example.com" required /></label>
            <label>Department<input name="department" value={form.department} onChange={handleFormChange} placeholder="e.g. Engineering" required /></label>
            <label>
              Shift Start
              <input name="shift_start" value={form.shift_start} onChange={handleFormChange} placeholder="09:30" pattern="^([01]\d|2[0-3]):[0-5]\d$" title="HH:MM in 24-hour IST" required />
            </label>
            <label>
              Shift End
              <input name="shift_end" value={form.shift_end} onChange={handleFormChange} placeholder="18:30" pattern="^([01]\d|2[0-3]):[0-5]\d$" title="HH:MM in 24-hour IST" required />
            </label>
            <label>Joined On<input name="joined_on" type="date" value={form.joined_on} onChange={handleFormChange} required /></label>
          </div>
          <button type="submit" disabled={submitting}>{submitting ? 'Saving…' : 'Create Employee'}</button>
        </form>
      )}

      {/* Filter */}
      <div className="filter-bar">
        <input
          placeholder="Filter by department…"
          value={deptFilter}
          onChange={e => setDeptFilter(e.target.value)}
        />
        <span className="total-label">{total} employee{total !== 1 ? 's' : ''}</span>
      </div>

      {error   && <p className="error">{error}</p>}
      {loading && <p className="loading">Loading…</p>}

      {!loading && items.length === 0 && <p className="empty">No employees found.</p>}

      {!loading && items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Emp Code</th><th>Name</th><th>Email</th>
              <th>Department</th><th>Shift</th><th>Joined On</th>
            </tr>
          </thead>
          <tbody>
            {items.map(e => (
              <tr key={e.emp_code}>
                <td><code>{e.emp_code}</code></td>
                <td>{e.name}</td>
                <td>{e.email}</td>
                <td>{e.department}</td>
                <td>{e.shift_start} – {e.shift_end}</td>
                <td>{e.joined_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} total={total} pageSize={PAGE_SIZE} onPage={handlePage} />
    </div>
  );
}
