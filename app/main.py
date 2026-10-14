"""
Employee Attendance & Analytics API

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import os
from typing import Annotated, Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

load_dotenv()

# MongoDB client and database connection
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True)
db = client[os.getenv("MONGO_DB", "attendance_db")]

# IST timezone: UTC + 5:30
IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #
def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def round_half_up(val: Optional[float], decimals: int = 2) -> Optional[float]:
    """Round a number using round-half-up (not banker's rounding)."""
    if val is None:
        return None
    d = Decimal(str(val))
    fmt = "0." + "0" * decimals if decimals > 0 else "0"
    return float(d.quantize(Decimal(fmt), rounding=ROUND_HALF_UP))


def truncate_ms(epoch_ms: int) -> int:
    """Truncate timestamp to whole seconds in epoch milliseconds."""
    return (epoch_ms // 1000) * 1000


def epoch_ms_to_datetime(epoch_ms: int) -> datetime:
    """Convert epoch milliseconds to a UTC datetime truncated to whole seconds."""
    truncated = truncate_ms(epoch_ms)
    return datetime.fromtimestamp(truncated / 1000, tz=timezone.utc)


def datetime_to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    """Convert a datetime object to integer epoch milliseconds."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def get_attendance_date(punch_in_dt: datetime, shift_start: str, shift_end: str) -> str:
    """
    Compute attendance date following Rule R1.
    For overnight shifts (shift_end <= shift_start), a punch-in whose IST time
    is strictly earlier than shift_end belongs to the shift starting the previous calendar day.
    """
    dt_ist = punch_in_dt.astimezone(IST)
    sh_h, sh_m = map(int, shift_start.split(":"))
    eh_h, eh_m = map(int, shift_end.split(":"))

    # Overnight shift check
    if (eh_h, eh_m) <= (sh_h, sh_m):
        if (dt_ist.hour, dt_ist.minute, dt_ist.second) < (eh_h, eh_m, 0):
            return (dt_ist.date() - timedelta(days=1)).isoformat()
    return dt_ist.date().isoformat()


def compute_late_minutes(punch_in_dt: datetime, shift_start: str, attendance_date: str) -> int:
    """
    Compute late minutes following Rule R2.
    Grace period is 10 minutes. A punch-in is late only if strictly more than
    10:00 (600 seconds) after shift start.
    When late, late_minutes = whole minutes elapsed since shift start. Otherwise 0.
    """
    dt_ist = punch_in_dt.astimezone(IST)
    sh_h, sh_m = map(int, shift_start.split(":"))
    start_dt = datetime.fromisoformat(attendance_date).replace(
        hour=sh_h, minute=sh_m, second=0, microsecond=0, tzinfo=IST
    )
    diff_seconds = (dt_ist - start_dt).total_seconds()
    if diff_seconds > 600:
        return int(diff_seconds // 60)
    return 0


def compute_work_hours(punch_in_dt: datetime, punch_out_dt: datetime) -> float:
    """
    Compute work hours following Rule R4.
    (punch_out - punch_in) in seconds / 3600, rounded to 2 decimals half-up.
    """
    seconds = (punch_out_dt - punch_in_dt).total_seconds()
    hours_dec = Decimal(str(seconds)) / Decimal("3600")
    return float(hours_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_overtime(punch_out_dt: datetime, shift_start: str, shift_end: str, attendance_date: str) -> int:
    """
    Compute overtime minutes following Rule R3.
    Whole minutes between shift_end and punch_out, counted only when >= 30; otherwise 0.
    For overnight shifts, shift_end falls on the next calendar day.
    """
    dt_ist = punch_out_dt.astimezone(IST)
    sh_h, sh_m = map(int, shift_start.split(":"))
    eh_h, eh_m = map(int, shift_end.split(":"))

    end_date = datetime.fromisoformat(attendance_date).date()
    if (eh_h, eh_m) <= (sh_h, sh_m):
        end_date += timedelta(days=1)

    end_dt = datetime.combine(end_date, datetime.min.time()).replace(
        hour=eh_h, minute=eh_m, second=0, microsecond=0, tzinfo=IST
    )
    diff_seconds = (dt_ist - end_dt).total_seconds()
    diff_minutes = int(diff_seconds // 60)
    return diff_minutes if diff_minutes >= 30 else 0


def format_employee_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format an employee document for the API response."""
    return {
        "emp_code": doc["emp_code"],
        "name": doc["name"],
        "email": doc["email"],
        "department": doc["department"],
        "shift_start": doc.get("shift_start", "09:30"),
        "shift_end": doc.get("shift_end", "18:30"),
        "joined_on": doc["joined_on"],
        "created_at": datetime_to_epoch_ms(doc.get("created_at")),
    }


def format_attendance_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format an attendance document for the API response, handling legacy fields and history."""
    raw_history = doc.get("history") or []
    history_list = []
    for h in raw_history:
        changes = {}
        for k, v in (h.get("changes") or {}).items():
            from_val = v.get("from")
            to_val = v.get("to")
            if k in ("punch_in", "punch_out"):
                if isinstance(from_val, datetime):
                    from_val = datetime_to_epoch_ms(from_val)
                if isinstance(to_val, datetime):
                    to_val = datetime_to_epoch_ms(to_val)
            changes[k] = {"from": from_val, "to": to_val}

        at_val = h.get("at")
        if isinstance(at_val, datetime):
            at_val = datetime_to_epoch_ms(at_val)

        history_list.append({
            "at": at_val,
            "by": h.get("by"),
            "reason": h.get("reason"),
            "changes": changes,
        })

    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": datetime_to_epoch_ms(doc.get("punch_in")),
        "punch_out": datetime_to_epoch_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": history_list,
    }


# --------------------------------------------------------------------------- #
# Request Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(..., min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field("18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    status: str = Field("PRESENT", pattern=r"^(PRESENT|WFH|ON_DUTY|ABSENT|LEAVE)$")


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)


class RegularizeIn(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$")
    punch_in: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    punch_out: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    reason: str = Field(..., min_length=5, max_length=200)
    regularized_by: str = Field(..., min_length=1, max_length=50)


# --------------------------------------------------------------------------- #
# Startup Event: Create MongoDB Indexes Idempotently
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def create_indexes():
    """Ensure all required indexes exist at startup."""
    # Unique index on emp_code for employees
    db.employees.create_index([("emp_code", 1)], unique=True)
    # Indexes to optimize department analytics and filtering
    db.employees.create_index([("department", 1), ("joined_on", 1)])
    db.employees.create_index([("joined_on", 1)])

    # Unique compound index on (emp_code, date) for attendance logs
    db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
    # Index for sorting and listing attendance records
    db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])
    # Index for fast punch-out lookup
    db.attendance_logs.create_index([("emp_code", 1), ("punch_in", -1)])
    # Indexes for leaderboard and analytics match stages
    db.attendance_logs.create_index([("date", 1), ("late_minutes", 1), ("emp_code", 1)])
    db.attendance_logs.create_index([("status", 1), ("date", -1), ("emp_code", 1)])


# --------------------------------------------------------------------------- #
# System Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    """Readiness probe. Returns 200 if MongoDB answers ping, else 503."""
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")


# --------------------------------------------------------------------------- #
# Employee Endpoints
# --------------------------------------------------------------------------- #
@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    """Create a new employee record."""
    if body.shift_start == body.shift_end:
        raise HTTPException(status_code=422, detail="shift_start and shift_end must differ")

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    doc = {
        "emp_code": body.emp_code,
        "name": body.name,
        "email": body.email,
        "department": body.department,
        "shift_start": body.shift_start,
        "shift_end": body.shift_end,
        "joined_on": body.joined_on,
        "created_at": now_utc,
    }
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="emp_code already exists")

    return format_employee_doc(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List employees sorted by emp_code ascending."""
    q: Dict[str, Any] = {}
    if department:
        q["department"] = department

    total = db.employees.count_documents(q)
    skip = (page - 1) * page_size
    cursor = db.employees.find(q).sort("emp_code", 1).skip(skip).limit(page_size)
    items = [format_employee_doc(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------- #
# Attendance Endpoints
# --------------------------------------------------------------------------- #
@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    """Record a punch-in event. ABSENT/LEAVE creates a record with no punch times."""
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.status in ("ABSENT", "LEAVE"):
        # No punch times for absent/leave — use today's IST date
        now_ist = datetime.now(IST)
        attendance_date = now_ist.date().isoformat()
        doc = {
            "emp_code": body.emp_code,
            "date": attendance_date,
            "status": body.status,
            "punch_in": None,
            "punch_out": None,
            "work_hours": None,
            "late_minutes": 0,
            "overtime_minutes": 0,
            "half_day": False,
            "history": [],
        }
    else:
        if body.punched_at is not None:
            punch_in_dt = epoch_ms_to_datetime(body.punched_at)
        else:
            punch_in_dt = datetime.now(timezone.utc).replace(microsecond=0)

        attendance_date = get_attendance_date(punch_in_dt, emp["shift_start"], emp["shift_end"])
        late_minutes = compute_late_minutes(punch_in_dt, emp["shift_start"], attendance_date)

        doc = {
            "emp_code": body.emp_code,
            "date": attendance_date,
            "status": body.status,
            "punch_in": punch_in_dt,
            "punch_out": None,
            "work_hours": None,
            "late_minutes": late_minutes,
            "overtime_minutes": 0,
            "half_day": False,
            "history": [],
        }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Attendance record already exists for this date")

    return format_attendance_doc(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    """Record a punch-out event for the most recent record."""
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.punched_at is not None:
        punch_out_dt = epoch_ms_to_datetime(body.punched_at)
    else:
        punch_out_dt = datetime.now(timezone.utc).replace(microsecond=0)

    # Find the employee's most recent attendance record
    target = db.attendance_logs.find_one(
        {"emp_code": body.emp_code},
        sort=[("punch_in", -1)],
    )
    if not target or target.get("punch_in") is None:
        raise HTTPException(status_code=404, detail="No punch-in found")

    punch_in_dt = ensure_utc(target["punch_in"])
    punch_out_dt = ensure_utc(punch_out_dt)

    if punch_out_dt <= punch_in_dt:
        raise HTTPException(status_code=422, detail="punch_out must be after punch_in")

    if (punch_out_dt - punch_in_dt).total_seconds() > 24 * 3600:
        raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    if target.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Record is already punched out")

    work_hours = compute_work_hours(punch_in_dt, punch_out_dt)
    half_day = bool(work_hours < 4.50)
    overtime_minutes = compute_overtime(punch_out_dt, emp["shift_start"], emp["shift_end"], target["date"])

    # Atomic update to ensure only one simultaneous punch-out succeeds
    updated = db.attendance_logs.find_one_and_update(
        {"_id": target["_id"], "punch_out": None},
        {
            "$set": {
                "punch_out": punch_out_dt,
                "work_hours": work_hours,
                "overtime_minutes": overtime_minutes,
                "half_day": half_day,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Record is already punched out")

    return format_attendance_doc(updated)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Annotated[Optional[str], Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    date_to: Annotated[Optional[str], Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    status: Annotated[Optional[str], Query(pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List attendance records with database-side sorting and pagination."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be greater than date_to")

    q: Dict[str, Any] = {}
    if emp_code:
        q["emp_code"] = emp_code
    if status:
        q["status"] = status
    if date_from or date_to:
        date_q: Dict[str, Any] = {}
        if date_from:
            date_q["$gte"] = date_from
        if date_to:
            date_q["$lte"] = date_to
        q["date"] = date_q

    total = db.attendance_logs.count_documents(q)
    skip = (page - 1) * page_size
    cursor = db.attendance_logs.find(q).sort([("date", -1), ("emp_code", 1)]).skip(skip).limit(page_size)
    items = [format_attendance_doc(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str = Path(...),
    date: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    body: RegularizeIn = ...,
):
    """Regularize (manually correct) one day's attendance record with audit history."""
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    doc = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not doc:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    # Determine desired status
    target_status = body.status if body.status is not None else doc["status"]

    if target_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(
                status_code=422,
                detail="ABSENT or LEAVE status clears both punch times; cannot provide punch_in or punch_out",
            )
        target_punch_in_dt = None
        target_punch_out_dt = None
    else:
        # Presence status requires punch_in
        if body.punch_in is not None:
            target_punch_in_dt = epoch_ms_to_datetime(body.punch_in)
        else:
            target_punch_in_dt = ensure_utc(doc.get("punch_in"))

        if target_punch_in_dt is None:
            raise HTTPException(status_code=422, detail="A presence status requires a punch_in")

        if body.punch_out is not None:
            target_punch_out_dt = epoch_ms_to_datetime(body.punch_out)
        else:
            target_punch_out_dt = ensure_utc(doc.get("punch_out"))

        target_punch_in_dt = ensure_utc(target_punch_in_dt)
        target_punch_out_dt = ensure_utc(target_punch_out_dt)

        # Validate that punch_in stays on the record's attendance date
        r1_date = get_attendance_date(target_punch_in_dt, emp["shift_start"], emp["shift_end"])
        if r1_date != date:
            raise HTTPException(status_code=422, detail="punch_in must stay on the record's attendance date")

        # Validate punch_out if present
        if target_punch_out_dt is not None:
            if target_punch_out_dt <= target_punch_in_dt:
                raise HTTPException(status_code=422, detail="punch_out must be after punch_in")
            if (target_punch_out_dt - target_punch_in_dt).total_seconds() > 24 * 3600:
                raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    # Recompute derived fields
    if target_status in ("ABSENT", "LEAVE"):
        new_work_hours = None
        new_late_minutes = 0
        new_overtime_minutes = 0
        new_half_day = False
    else:
        new_late_minutes = compute_late_minutes(target_punch_in_dt, emp["shift_start"], date)
        if target_punch_out_dt is not None:
            new_work_hours = compute_work_hours(target_punch_in_dt, target_punch_out_dt)
            new_half_day = bool(new_work_hours < 4.50)
            new_overtime_minutes = compute_overtime(
                target_punch_out_dt, emp["shift_start"], emp["shift_end"], date
            )
        else:
            new_work_hours = None
            new_half_day = False
            new_overtime_minutes = 0

    # Detect fields that actually changed
    changes_mongo: Dict[str, Any] = {}

    old_status = doc.get("status")
    if old_status != target_status:
        changes_mongo["status"] = {"from": old_status, "to": target_status}

    old_punch_in = ensure_utc(doc.get("punch_in"))
    if old_punch_in != target_punch_in_dt:
        changes_mongo["punch_in"] = {"from": old_punch_in, "to": target_punch_in_dt}

    old_punch_out = ensure_utc(doc.get("punch_out"))
    if old_punch_out != target_punch_out_dt:
        changes_mongo["punch_out"] = {"from": old_punch_out, "to": target_punch_out_dt}

    old_work_hours = doc.get("work_hours")
    if old_work_hours != new_work_hours:
        changes_mongo["work_hours"] = {"from": old_work_hours, "to": new_work_hours}

    old_late = doc.get("late_minutes", 0)
    if old_late != new_late_minutes:
        changes_mongo["late_minutes"] = {"from": old_late, "to": new_late_minutes}

    old_ot = doc.get("overtime_minutes", 0)
    if old_ot != new_overtime_minutes:
        changes_mongo["overtime_minutes"] = {"from": old_ot, "to": new_overtime_minutes}

    old_half_day = doc.get("half_day", False)
    if old_half_day != new_half_day:
        changes_mongo["half_day"] = {"from": old_half_day, "to": new_half_day}

    if not changes_mongo:
        raise HTTPException(status_code=422, detail="No fields were changed")

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    history_entry = {
        "at": now_utc,
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes_mongo,
    }

    # Optimistic concurrency check: match current history length so concurrent edits don't overwrite each other
    current_history_len = len(doc.get("history") or [])
    res = db.attendance_logs.update_one(
        {"_id": doc["_id"], f"history.{current_history_len}": {"$exists": False}},
        {
            "$set": {
                "status": target_status,
                "punch_in": target_punch_in_dt,
                "punch_out": target_punch_out_dt,
                "work_hours": new_work_hours,
                "late_minutes": new_late_minutes,
                "overtime_minutes": new_overtime_minutes,
                "half_day": new_half_day,
            },
            "$push": {"history": history_entry},
        },
    )

    if res.modified_count == 0:
        raise HTTPException(status_code=409, detail="Concurrent modification conflict")

    updated_doc = db.attendance_logs.find_one({"_id": doc["_id"]})
    return format_attendance_doc(updated_doc)


# --------------------------------------------------------------------------- #
# Analytics Endpoints
# --------------------------------------------------------------------------- #
@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str = Path(...),
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = ...,
):
    """Monthly attendance summary for one employee backed by MongoDB aggregation."""
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    year, month_num = map(int, month.split("-"))
    month_start = date(year, month_num, 1)
    last_day_num = calendar.monthrange(year, month_num)[1]
    month_end = date(year, month_num, last_day_num)

    # Compute working days (Mon-Fri) from joined_on (Rule R7)
    emp_joined = date.fromisoformat(emp["joined_on"])
    if emp_joined > month_end:
        working_days = 0
    else:
        eff_start = max(month_start, emp_joined)
        working_days = sum(
            1 for d in range((month_end - eff_start).days + 1)
            if (eff_start + timedelta(days=d)).weekday() < 5
        )

    month_start_str = f"{month}-01"
    month_end_str = f"{month}-{last_day_num:02d}"

    # MongoDB aggregation pipeline for monthly attendance
    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$gte": month_start_str, "$lte": month_end_str},
            }
        },
        {
            "$project": {
                "date": 1,
                "status": 1,
                "half_day": 1,
                "late_minutes": {"$ifNull": ["$late_minutes", 0]},
                "overtime_minutes": {"$ifNull": ["$overtime_minutes", 0]},
                "dayOfWeek": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}},
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
                                ]
                            },
                            {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}
                },
                "total_late_minutes": {"$sum": "$late_minutes"},
                "total_overtime_minutes": {"$sum": "$overtime_minutes"},
            }
        },
    ]

    agg_res = list(db.attendance_logs.aggregate(pipeline))
    if agg_res:
        row = agg_res[0]
        present_days = float(row.get("present_days", 0.0))
        leave_days = int(row.get("leave_days", 0))
        late_count = int(row.get("late_count", 0))
        total_late_minutes = int(row.get("total_late_minutes", 0))
        total_overtime_minutes = int(row.get("total_overtime_minutes", 0))
    else:
        present_days = 0.0
        leave_days = 0
        late_count = 0
        total_late_minutes = 0
        total_overtime_minutes = 0

    if working_days > 0:
        raw_pct = (present_days / working_days) * 100
        attendance_pct = round_half_up(raw_pct, 2)
    else:
        attendance_pct = None

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": leave_days,
        "late_count": late_count,
        "total_late_minutes": total_late_minutes,
        "total_overtime_minutes": total_overtime_minutes,
        "attendance_pct": attendance_pct,
    }


@app.get("/analytics/departments/summary")
def department_summary(
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = ...,
    department: Optional[str] = None,
):
    """Department summary for a month aggregated across employees and attendance collections."""
    year, month_num = map(int, month.split("-"))
    last_day_num = calendar.monthrange(year, month_num)[1]
    month_start_str = f"{month}-01"
    month_end_str = f"{month}-{last_day_num:02d}"

    match_stage: Dict[str, Any] = {"joined_on": {"$lte": month_end_str}}
    if department:
        match_stage["department"] = department

    pipeline = [
        # Match employees who joined on or before the end of the month
        {"$match": match_stage},
        # Lookup attendance logs for the month
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$emp"]},
                                    {"$gte": ["$date", month_start_str]},
                                    {"$lte": ["$date", month_end_str]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        # Group by department to count headcount and collect logs
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1},
                "all_logs": {"$push": "$logs"},
            }
        },
        # Flatten all logs for the department
        {
            "$project": {
                "department": "$_id",
                "headcount": 1,
                "logs": {
                    "$reduce": {
                        "input": "$all_logs",
                        "initialValue": [],
                        "in": {"$concatArrays": ["$$value", "$$this"]},
                    }
                },
            }
        },
        # Calculate department metrics
        {
            "$project": {
                "department": 1,
                "headcount": 1,
                "present_days": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {
                                "$cond": [
                                    {
                                        "$and": [
                                            {"$in": ["$$log.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                            {
                                                "$in": [
                                                    {"$dayOfWeek": {"$dateFromString": {"dateString": "$$log.date"}}},
                                                    [2, 3, 4, 5, 6],
                                                ]
                                            },
                                        ]
                                    },
                                    {"$cond": [{"$eq": ["$$log.half_day", True]}, 0.5, 1.0]},
                                    0.0,
                                ]
                            },
                        }
                    }
                },
                "late_count": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {
                                "$cond": [
                                    {"$gt": [{"$ifNull": ["$$log.late_minutes", 0]}, 0]},
                                    1,
                                    0,
                                ]
                            },
                        }
                    }
                },
                "total_late_minutes": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {"$ifNull": ["$$log.late_minutes", 0]},
                        }
                    }
                },
                "leave_count": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {"$cond": [{"$eq": ["$$log.status", "LEAVE"]}, 1, 0]},
                        }
                    }
                },
                "on_duty_count": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {"$cond": [{"$eq": ["$$log.status", "ON_DUTY"]}, 1, 0]},
                        }
                    }
                },
                "present_work_hours": {
                    "$filter": {
                        "input": {
                            "$map": {
                                "input": "$logs",
                                "as": "log",
                                "in": {
                                    "$cond": [
                                        {
                                            "$and": [
                                                {"$in": ["$$log.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                                {"$ne": ["$$log.work_hours", None]},
                                            ]
                                        },
                                        "$$log.work_hours",
                                        None,
                                    ]
                                },
                            }
                        },
                        "as": "wh",
                        "cond": {"$ne": ["$$wh", None]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": 1,
                "headcount": 1,
                "present_days": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
                "avg_work_hours": {
                    "$cond": [
                        {"$gt": [{"$size": "$present_work_hours"}, 0]},
                        {"$avg": "$present_work_hours"},
                        None,
                    ]
                },
            }
        },
        {"$sort": {"department": 1}},
    ]

    raw_items = list(db.employees.aggregate(pipeline))
    items = []
    for item in raw_items:
        items.append({
            "department": item["department"],
            "headcount": item["headcount"],
            "present_days": float(item.get("present_days", 0.0)),
            "avg_work_hours": round_half_up(item.get("avg_work_hours"), 2),
            "late_count": int(item.get("late_count", 0)),
            "total_late_minutes": int(item.get("total_late_minutes", 0)),
            "leave_count": int(item.get("leave_count", 0)),
            "on_duty_count": int(item.get("on_duty_count", 0)),
        })

    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = ...,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    department: Optional[str] = None,
):
    """Late-comers leaderboard with standard competition ranking and tie handling."""
    year, month_num = map(int, month.split("-"))
    last_day_num = calendar.monthrange(year, month_num)[1]
    month_start_str = f"{month}-01"
    month_end_str = f"{month}-{last_day_num:02d}"

    pipeline: List[Dict[str, Any]] = [
        {
            "$match": {
                "date": {"$gte": month_start_str, "$lte": month_end_str},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp",
            }
        },
        {"$unwind": "$emp"},
    ]

    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.extend([
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": 1,
                "late_count": 1,
            }
        },
        # Standard competition ranking using $rank window function
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {
                    "rank": {"$rank": {}}
                },
            }
        },
        # Limit applies after ranking
        {"$match": {"rank": {"$lte": limit}}},
        # Final ordering: total_late_minutes desc, emp_code asc
        {
            "$sort": {
                "total_late_minutes": -1,
                "emp_code": 1,
            }
        },
    ])

    items = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "items": items}


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str = Path(...),
    from_date: Annotated[str, Query(alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$")] = ...,
    to_date: Annotated[str, Query(alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$")] = ...,
):
    """Daily attendance trend for a department with gap filling ($densify) and 7-day moving average."""
    dept_exists = db.employees.find_one({"department": department})
    if not dept_exists:
        raise HTTPException(status_code=404, detail="Department not found")

    d_from = date.fromisoformat(from_date)
    d_to = date.fromisoformat(to_date)
    if d_to < d_from:
        raise HTTPException(status_code=422, detail="'to' date cannot be before 'from' date")

    days_count = (d_to - d_from).days + 1
    if days_count > 92:
        raise HTTPException(status_code=422, detail="Date range exceeds 92 days")

    from_dt = datetime.fromisoformat(from_date + "T00:00:00Z")
    to_dt = datetime.fromisoformat(to_date + "T00:00:00Z") + timedelta(days=1)

    # Fetch employee codes for department to allow indexed $in query on attendance_logs
    emp_codes = [
        e["emp_code"]
        for e in db.employees.find({"department": department}, {"_id": 0, "emp_code": 1})
    ]

    pipeline = [
        # Match attendance logs using index scan
        {
            "$match": {
                "emp_code": {"$in": emp_codes},
                "date": {"$gte": from_date, "$lte": to_date},
            }
        },
        # Group by date to aggregate present and late logs
        {
            "$group": {
                "_id": "$date",
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                            {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "date_str": "$_id",
                "date_dt": {"$dateFromString": {"dateString": "$_id"}},
                "present_count": 1,
                "late_count": 1,
            }
        },
        # Gap-filling: densify across the full date range
        {
            "$densify": {
                "field": "date_dt",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [from_dt, to_dt],
                },
            }
        },
        # Fill defaults for missing dates
        {
            "$set": {
                "date": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$date_dt",
                    }
                },
                "present_count": {"$ifNull": ["$present_count", 0.0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
            }
        },
        # Lookup headcount for each calendar day
        {
            "$lookup": {
                "from": "employees",
                "let": {"day_str": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$day_str"]},
                                ]
                            }
                        }
                    },
                    {"$count": "count"},
                ],
                "as": "hc",
            }
        },
        {
            "$set": {
                "headcount": {"$ifNull": [{"$arrayElemAt": ["$hc.count", 0]}, 0]},
                "dayOfWeek": {"$dayOfWeek": "$date_dt"},
            }
        },
        # Mon-Fri are working days (dayOfWeek: 2=Mon, 6=Fri)
        {
            "$set": {
                "is_working_day": {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]}
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                {"$eq": ["$is_working_day", True]},
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {"$divide": ["$present_count", "$headcount"]},
                        None,
                    ]
                }
            }
        },
        {"$sort": {"date": 1}},
        # 7-day moving average over preceding non-null attendance_rate rows in range
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {
                            "documents": [-6, "current"],
                        },
                    }
                },
            }
        },
    ]

    raw_items = list(db.attendance_logs.aggregate(pipeline))
    items = []
    for r in raw_items:
        items.append({
            "date": r["date"],
            "is_working_day": r["is_working_day"],
            "headcount": r["headcount"],
            "present_count": float(r["present_count"]),
            "late_count": int(r["late_count"]),
            "attendance_rate": round_half_up(r["attendance_rate"], 4),
            "moving_avg_7d": round_half_up(r["moving_avg_7d"], 4),
        })

    return {"department": department, "items": items}


# --------------------------------------------------------------------------- #
# Admin Explain Endpoint
# --------------------------------------------------------------------------- #
@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str = Path(...),
    emp_code: Optional[str] = None,
    month: Annotated[Optional[str], Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    department: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    date_from: Annotated[Optional[str], Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    date_to: Annotated[Optional[str], Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    status: Annotated[Optional[str], Query(pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$")] = None,
    from_date: Annotated[Optional[str], Query(alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    to_date: Annotated[Optional[str], Query(alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Run MongoDB explain with executionStats verbosity for an endpoint's main query."""
    valid_endpoints = [
        "attendance_list",
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
        "department_trend",
    ]
    if endpoint not in valid_endpoints:
        raise HTTPException(status_code=422, detail=f"Invalid endpoint. Must be one of {valid_endpoints}")

    if endpoint == "attendance_list":
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from cannot be greater than date_to")
        q: Dict[str, Any] = {}
        if emp_code:
            q["emp_code"] = emp_code
        if status:
            q["status"] = status
        if date_from or date_to:
            date_q: Dict[str, Any] = {}
            if date_from:
                date_q["$gte"] = date_from
            if date_to:
                date_q["$lte"] = date_to
            q["date"] = date_q

        exp = db.command(
            "explain",
            {
                "find": "attendance_logs",
                "filter": q,
                "sort": {"date": -1, "emp_code": 1},
                "skip": (page - 1) * page_size,
                "limit": page_size,
            },
            verbosity="executionStats",
        )
        return {"endpoint": "attendance_list", "collection": "attendance_logs", "explain": exp}

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(status_code=422, detail="emp_code and month are required for employee_monthly")

        year, month_num = map(int, month.split("-"))
        last_day_num = calendar.monthrange(year, month_num)[1]
        month_start_str = f"{month}-01"
        month_end_str = f"{month}-{last_day_num:02d}"

        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {"$gte": month_start_str, "$lte": month_end_str},
                }
            },
            {
                "$project": {
                    "date": 1,
                    "status": 1,
                    "half_day": 1,
                    "late_minutes": {"$ifNull": ["$late_minutes", 0]},
                    "overtime_minutes": {"$ifNull": ["$overtime_minutes", 0]},
                    "dayOfWeek": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                        {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
                                    ]
                                },
                                {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]},
                                0.0,
                            ]
                        }
                    },
                    "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
                    "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                    "total_late_minutes": {"$sum": "$late_minutes"},
                    "total_overtime_minutes": {"$sum": "$overtime_minutes"},
                }
            },
        ]
        exp = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {"endpoint": "employee_monthly", "collection": "attendance_logs", "explain": exp}

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month is required for department_summary")

        year, month_num = map(int, month.split("-"))
        last_day_num = calendar.monthrange(year, month_num)[1]
        month_start_str = f"{month}-01"
        month_end_str = f"{month}-{last_day_num:02d}"

        match_stage = {"joined_on": {"$lte": month_end_str}}
        if department:
            match_stage["department"] = department

        pipeline = [
            {"$match": match_stage},
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"emp": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$emp_code", "$$emp"]},
                                        {"$gte": ["$date", month_start_str]},
                                        {"$lte": ["$date", month_end_str]},
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "logs",
                }
            },
            {
                "$group": {
                    "_id": "$department",
                    "headcount": {"$sum": 1},
                    "all_logs": {"$push": "$logs"},
                }
            },
            {
                "$project": {
                    "department": "$_id",
                    "headcount": 1,
                    "logs": {
                        "$reduce": {
                            "input": "$all_logs",
                            "initialValue": [],
                            "in": {"$concatArrays": ["$$value", "$$this"]},
                        }
                    },
                }
            },
            {"$sort": {"department": 1}},
        ]

        exp = db.command(
            "explain",
            {"aggregate": "employees", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {"endpoint": "department_summary", "collection": "employees", "explain": exp}

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month is required for late_leaderboard")

        year, month_num = map(int, month.split("-"))
        last_day_num = calendar.monthrange(year, month_num)[1]
        month_start_str = f"{month}-01"
        month_end_str = f"{month}-{last_day_num:02d}"

        pipeline = [
            {
                "$match": {
                    "date": {"$gte": month_start_str, "$lte": month_end_str},
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {"$sum": "$late_minutes"},
                    "late_count": {"$sum": 1},
                }
            },
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "_id",
                    "foreignField": "emp_code",
                    "as": "emp",
                }
            },
            {"$unwind": "$emp"},
        ]
        if department:
            pipeline.append({"$match": {"emp.department": department}})

        pipeline.extend([
            {
                "$setWindowFields": {
                    "sortBy": {"total_late_minutes": -1},
                    "output": {"rank": {"$rank": {}}},
                }
            },
            {"$match": {"rank": {"$lte": limit}}},
            {"$sort": {"total_late_minutes": -1, "emp_code": 1}},
        ])

        exp = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {"endpoint": "late_leaderboard", "collection": "attendance_logs", "explain": exp}

    elif endpoint == "department_trend":
        if not department or not from_date or not to_date:
            raise HTTPException(
                status_code=422,
                detail="department, from, and to are required for department_trend",
            )

        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
        if d_to < d_from:
            raise HTTPException(status_code=422, detail="'to' date cannot be before 'from' date")
        if (d_to - d_from).days + 1 > 92:
            raise HTTPException(status_code=422, detail="Date range exceeds 92 days")

        from_dt = datetime.fromisoformat(from_date + "T00:00:00Z")
        to_dt = datetime.fromisoformat(to_date + "T00:00:00Z") + timedelta(days=1)

        emp_codes = [
            e["emp_code"]
            for e in db.employees.find({"department": department}, {"_id": 0, "emp_code": 1})
        ]

        pipeline = [
            {
                "$match": {
                    "emp_code": {"$in": emp_codes},
                    "date": {"$gte": from_date, "$lte": to_date},
                }
            },
            {
                "$group": {
                    "_id": "$date",
                    "present_count": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]},
                                0.0,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {
                "$project": {
                    "date_str": "$_id",
                    "date_dt": {"$dateFromString": {"dateString": "$_id"}},
                    "present_count": 1,
                    "late_count": 1,
                }
            },
            {
                "$densify": {
                    "field": "date_dt",
                    "range": {
                        "step": 1,
                        "unit": "day",
                        "bounds": [from_dt, to_dt],
                    },
                }
            },
            {"$sort": {"date_dt": 1}},
        ]

        exp = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {"endpoint": "department_trend", "collection": "attendance_logs", "explain": exp}
