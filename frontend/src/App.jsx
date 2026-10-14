import { useState } from 'react';
import Dashboard   from './pages/Dashboard';
import Employees   from './pages/Employees';
import Attendance  from './pages/Attendance';
import Corrections from './pages/Corrections';
import Analytics   from './pages/Analytics';
import './App.css';

const PAGES = [
  { id: 'dashboard',   label: '🏠 Dashboard',    Component: Dashboard },
  { id: 'employees',   label: '👥 Employees',     Component: Employees },
  { id: 'attendance',  label: '🕐 Attendance',    Component: Attendance },
  { id: 'corrections', label: '✏️ Corrections',   Component: Corrections },
  { id: 'analytics',   label: '📊 Analytics',     Component: Analytics },
];

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const { Component } = PAGES.find(p => p.id === activePage);

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span>📋</span>
          <span>AttendanceHR</span>
        </div>
        <nav>
          {PAGES.map(p => (
            <button
              key={p.id}
              className={`nav-btn${activePage === p.id ? ' active' : ''}`}
              onClick={() => setActivePage(p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          FastAPI · MongoDB · React<br />
          Attendance &amp; Analytics v2.0
        </div>
      </aside>

      {/* Main content */}
      <div className="main-area">
        <header className="top-header">
          <span className="header-title">Employee Attendance &amp; Analytics</span>
          <span className="header-sub">FastAPI · MongoDB · React</span>
        </header>
        <main className="content">
          <Component />
        </main>
      </div>
    </div>
  );
}
