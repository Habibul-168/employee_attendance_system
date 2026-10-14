import { useState } from 'react';
import { regularizeAttendance, getAttendance } from '../api/client';
import StatusBadge from '../components/StatusBadge';

// Convert epoch ms → "YYYY-MM-DDThh:mm" for datetime-local input
function msToInputVal(ms) {
  if (!ms) return '';
  const d = new Date(ms);
  // Show in IST
  const ist = new Date(d.getTime() + 5.5 * 60 * 60 * 1000);
  return ist.toISOString().slice(0, 16);
}

// Convert "YYYY-MM-DDThh:mm" (treated as IST) → epoch ms
function inputValToMs(val) {
  if (!val) return null;
  // Append IST offset so the server receives the right UTC time
  const dt = new Date(val + ':00+05:30');
  return dt.getTime();
}

function fmtMs(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
}

const STATUSES = ['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'];

export default function Corrections() {
  // Step 1: look up the record
  const [lookupEmp, setLookupEmp]   = useState('');
  const [lookupDate, setLookupDate] = useState('');
  const [record, setRecord]         = useState(null);
  const [lookupErr, setLookupErr]   = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);

  // Step 2: correction form
  const [status, setStatus]         = useState('');
  const [punchIn, setPunchIn]       = useState('');
  const [punchOut, setPunchOut]     = useState('');
  const [reason, setReason]         = useState('');
  const [by, setBy]                 = useState('');
  const [submitErr, setSubmitErr]   = useState('');
  const [submitMsg, setSubmitMsg]   = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleLookup(e) {
    e.preventDefault();
    setLookupErr(''); setRecord(null); setSubmitErr(''); setSubmitMsg('');
    setLookupLoading(true);
    try {
      const data = await getAttendance({ emp_code: lookupEmp, date_from: lookupDate, date_to: lookupDate, page_size: 1 });
      if (!data.items.length) {
        setLookupErr('No attendance record found for that employee and date.');
      } else {
        const r = data.items[0];
        setRecord(r);
        setStatus(r.status);
        setPunchIn(msToInputVal(r.punch_in));
        setPunchOut(msToInputVal(r.punch_out));
      }
    } catch (err) {
      setLookupErr(err.message);
    } finally {
      setLookupLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitErr(''); setSubmitMsg('');
    setSubmitting(true);

    const body = { reason, regularized_by: by };
    if (status)   body.status    = status;
    if (punchIn)  body.punch_in  = inputValToMs(punchIn);
    if (punchOut) body.punch_out = inputValToMs(punchOut);

    try {
      const updated = await regularizeAttendance(lookupEmp, lookupDate, body);
      setSubmitMsg('Correction saved successfully.');
      setRecord(updated);
      setStatus(updated.status);
      setPunchIn(msToInputVal(updated.punch_in));
      setPunchOut(msToInputVal(updated.punch_out));
    } catch (err) {
      setSubmitErr(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const noTimes = status === 'ABSENT' || status === 'LEAVE';

  return (
    <div>
      <h2>Attendance Correction</h2>

      {/* Lookup form */}
      <form className="form-card" onSubmit={handleLookup} style={{ maxWidth: 480 }}>
        <h3>Find Record</h3>
        {lookupErr && <p className="error">{lookupErr}</p>}
        <label>Emp Code
          <input value={lookupEmp} onChange={e => setLookupEmp(e.target.value)} placeholder="EMP0001" required />
        </label>
        <label>Date
          <input type="date" value={lookupDate} onChange={e => setLookupDate(e.target.value)} required />
        </label>
        <button type="submit" disabled={lookupLoading}>{lookupLoading ? 'Looking up…' : 'Find Record'}</button>
      </form>

      {/* Current record summary */}
      {record && (
        <>
          <div className="info-box">
            <strong>Current Record:</strong>&nbsp;
            {record.emp_code} · {record.date} · <StatusBadge status={record.status} />
            &nbsp;· Punch In: {fmtMs(record.punch_in)}
            &nbsp;· Punch Out: {fmtMs(record.punch_out)}
            &nbsp;· Work Hours: {record.work_hours ?? '—'}
          </div>

          {/* Correction form */}
          <form className="form-card" onSubmit={handleSubmit}>
            <h3>Make Correction</h3>
            {submitErr && <p className="error">{submitErr}</p>}
            {submitMsg && <p className="success">{submitMsg}</p>}
            <div className="form-grid">
              <label>Status
                <select value={status} onChange={e => setStatus(e.target.value)}>
                  {STATUSES.map(s => <option key={s}>{s}</option>)}
                </select>
              </label>
              {!noTimes && (
                <>
                  <label>Punch In (IST)
                    <input type="datetime-local" value={punchIn} onChange={e => setPunchIn(e.target.value)} />
                  </label>
                  <label>Punch Out (IST)
                    <input type="datetime-local" value={punchOut} onChange={e => setPunchOut(e.target.value)} />
                  </label>
                </>
              )}
              <label>Corrected By
                <input value={by} onChange={e => setBy(e.target.value)} placeholder="hr.admin" required />
              </label>
              <label>Reason
                <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Minimum 5 characters" required minLength={5} />
              </label>
            </div>
            <button type="submit" disabled={submitting}>{submitting ? 'Saving…' : 'Submit Correction'}</button>
          </form>

          {/* Audit history */}
          <h3>Correction History</h3>
          {(!record.history || record.history.length === 0) ? (
            <p className="empty">No corrections have been made to this record.</p>
          ) : (
            <table>
              <thead>
                <tr><th>When (IST)</th><th>By</th><th>Reason</th><th>Changes</th></tr>
              </thead>
              <tbody>
                {record.history.map((h, i) => (
                  <tr key={i}>
                    <td>{fmtMs(h.at)}</td>
                    <td>{h.by}</td>
                    <td>{h.reason}</td>
                    <td>
                      {Object.entries(h.changes || {}).map(([field, val]) => (
                        <div key={field} style={{ fontSize: '0.82rem' }}>
                          <strong>{field}:</strong>{' '}
                          {field === 'punch_in' || field === 'punch_out'
                            ? `${fmtMs(val.from)} → ${fmtMs(val.to)}`
                            : `${val.from} → ${val.to}`}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
