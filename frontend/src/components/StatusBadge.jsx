// Colored badge for attendance status values
const COLORS = {
  PRESENT:  '#22c55e',
  WFH:      '#3b82f6',
  ON_DUTY:  '#a855f7',
  ABSENT:   '#ef4444',
  LEAVE:    '#f59e0b',
};

export default function StatusBadge({ status }) {
  const color = COLORS[status] || '#6b7280';
  return (
    <span style={{
      background: color,
      color: '#fff',
      padding: '2px 10px',
      borderRadius: '12px',
      fontSize: '0.78rem',
      fontWeight: 600,
      letterSpacing: '0.03em',
    }}>
      {status}
    </span>
  );
}
