# Employee Attendance & Analytics System

A full-stack HR attendance management system built with **FastAPI**, **MongoDB**, and **React + Vite**.

## Features

- Employee management with department filtering and pagination
- Punch-in / punch-out with IST timezone, overnight shift support, grace period, overtime, and half-day calculation
- Attendance listing with filters and pagination
- HR attendance corrections with full audit history and optimistic concurrency
- Analytics: employee monthly summary, department summary, late-comers leaderboard, department daily trend
- MongoDB aggregation pipelines with index-backed queries
- React dashboard with 5 pages: Dashboard, Employees, Attendance, Corrections, Analytics

## Technology Stack

| Layer    | Technology                        |
|----------|-----------------------------------|
| Backend  | Python 3.10+, FastAPI, PyMongo    |
| Database | MongoDB 6.0+                      |
| Frontend | React 18, Vite, plain CSS         |

## Prerequisites

- Python 3.10+
- MongoDB 6.0+ running locally on port 27017
- Node.js 18+ and npm

## Environment Variables

Create a `.env` file in the project root (next to `app/`):

```ini
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

Create a `.env` file in `frontend/`:

```ini
VITE_API_BASE_URL=http://localhost:8000
```

Never commit `.env` files.

## Backend Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed sample data into MongoDB
python sample_seed.py

# 4. Start the API server
uvicorn app.main:app --port 8000 --reload
```

Interactive API docs: http://localhost:8000/docs

## Frontend Setup

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Start the development server
npm run dev
```

Frontend runs at: http://localhost:5173

## Project Structure

```
candidate_kit/
├── app/
│   └── main.py          # Complete FastAPI application
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js        # All API calls in one place
│   │   ├── components/
│   │   │   ├── Pagination.jsx
│   │   │   └── StatusBadge.jsx
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Employees.jsx
│   │   │   ├── Attendance.jsx
│   │   │   ├── Corrections.jsx
│   │   │   └── Analytics.jsx
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── main.jsx
│   ├── .env
│   └── package.json
├── sample_data/
│   ├── employees.json
│   └── attendance_logs.json
├── DATA_MODEL.md
├── DECISIONS.md
├── REVIEW.md
├── openapi.yaml
├── requirements.txt
└── sample_seed.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | MongoDB readiness probe |
| POST | /employees | Create employee |
| GET | /employees | List employees (filter, paginate) |
| POST | /attendance/punch-in | Record punch-in |
| POST | /attendance/punch-out | Record punch-out |
| GET | /attendance | List attendance records |
| PATCH | /attendance/{emp_code}/{date} | Correct attendance (HR) |
| GET | /analytics/employees/{emp_code}/monthly | Employee monthly summary |
| GET | /analytics/departments/summary | Department summary |
| GET | /analytics/leaderboard/late | Late-comers leaderboard |
| GET | /analytics/departments/{department}/trend | Department daily trend |
| GET | /admin/explain/{endpoint} | MongoDB query plan |

## Key Implementation Decisions

See `DECISIONS.md` for detailed explanations of:
- Index choices and why
- Concurrent punch-in safety via unique compound index
- Standard competition ranking (1, 2, 2, 4) for leaderboard ties
- Headcount including employees with zero attendance logs
- Scalability improvement for 100× data volume

## Defects Fixed

See `REVIEW.md` for a full table of 24 defects found in the starter code and how each was fixed.
