import os
import json
import secrets
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ============================================================
# LANDLENS BACKEND
# FastAPI + PostgreSQL
# Render-compatible
# ============================================================

app = FastAPI(
    title="LANDLENS Enterprise Platform",
    version="1.0.0"
)

# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is not configured on the server."
        )

    try:
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor
        )
    except Exception as e:
        print("DATABASE CONNECTION ERROR:", e)
        raise HTTPException(
            status_code=500,
            detail="Could not connect to database."
        )

# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is missing.")
        return

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:
            # Main parcel table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parcels (
                    parcel_id TEXT PRIMARY KEY,
                    village_id INTEGER,
                    survey_no TEXT,
                    gat_no TEXT,
                    cts_no TEXT,
                    reference_ror TEXT,
                    old_area REAL DEFAULT 0,
                    new_area REAL DEFAULT 0,
                    old_survey_year INTEGER,
                    old_survey_method TEXT,
                    new_survey_method TEXT,
                    old_north REAL,
                    old_south REAL,
                    old_east REAL,
                    old_west REAL,
                    points_text TEXT,
                    geom_json TEXT,
                    instrument_type TEXT,
                    accuracy_m REAL,
                    calculated_area REAL,
                    submitted_by TEXT,
                    survey_timestamp TEXT,
                    quality_status TEXT DEFAULT 'REVIEW REQUIRED',
                    ai_risk_score REAL DEFAULT 0,
                    ai_risk_type TEXT,
                    verification_status TEXT DEFAULT 'PENDING',
                    audit_notes TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

        print("LANDLENS database initialized successfully.")

    except Exception as e:
        if conn:
            conn.rollback()
        print("DATABASE INITIALIZATION ERROR:", e)

    finally:
        if conn:
            conn.close()

# Run database initialization
init_db()

# ============================================================
# DEMO AUTHENTICATION
# ============================================================

DEMO_USERS = {
    "surveyor": {
        "password": "pass123",
        "gov_id": "GOV-SURV",
        "role": "SURVEYOR"
    },
    "surveyhead": {
        "password": "pass123",
        "gov_id": "GOV-HEAD",
        "role": "SURVEY_HEAD"
    },
    "officer": {
        "password": "pass123",
        "gov_id": "GOV-OFFICER",
        "role": "OFFICER"
    },
    "admin": {
        "password": "admin123",
        "gov_id": "GOV-ADMIN",
        "role": "ADMIN"
    }
}

ACTIVE_TOKENS = {}

# ============================================================
# Pydantic Models
# ============================================================

class RegisterData(BaseModel):
    parcel_id: str
    village_id: int = 1
    survey_no: str | None = None
    gat_no: str | None = None
    cts_no: str | None = None
    old_area: float = 0
    new_area: float = 0
    old_survey_year: int | None = None
    old_survey_method: str | None = None
    new_survey_method: str | None = None
    audit_notes: str | None = None

class OldRecordData(BaseModel):
    parcel_id: str
    reference_ror: str | None = None
    old_survey_no: str | None = None
    old_survey_year: int | None = None
    old_method: str | None = None
    north_dim: float | None = None
    south_dim: float | None = None
    east_dim: float | None = None
    west_dim: float | None = None

class ModernSurveyData(BaseModel):
    parcel_id: str
    instrument_type: str
    points_text: str
    accuracy_m: float | None = None
    calculated_area: float | None = None
    submitted_by: str | None = None
    survey_timestamp: str | None = None

class StatusUpdateData(BaseModel):
    parcel_id: str
    verification_status: str
    reviewer_role: str | None = None

# ============================================================
# API ENDPOINTS
# ============================================================

@app.post("/api/auth/login")
def login(username: str = Form(...), password: str = Form(...)):
    user_record = DEMO_USERS.get(username.lower())
    if not user_record or user_record["password"] != password:
        raise HTTPException(status_code=400, detail="Invalid username or password")
    
    token = secrets.token_hex(16)
    ACTIVE_TOKENS[token] = username
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user_record["role"],
        "gov_id": user_record["gov_id"]
    }

@app.post("/api/parcels/register")
def register_parcel(data: RegisterData):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parcels (
                    parcel_id, village_id, survey_no, gat_no, cts_no, 
                    old_area, new_area, old_survey_year, old_survey_method, 
                    new_survey_method, audit_notes, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (parcel_id) DO UPDATE SET
                    village_id = EXCLUDED.village_id,
                    survey_no = EXCLUDED.survey_no,
                    gat_no = EXCLUDED.gat_no,
                    cts_no = EXCLUDED.cts_no,
                    old_area = EXCLUDED.old_area,
                    new_area = EXCLUDED.new_area,
                    old_survey_year = EXCLUDED.old_survey_year,
                    old_survey_method = EXCLUDED.old_survey_method,
                    new_survey_method = EXCLUDED.new_survey_method,
                    audit_notes = EXCLUDED.audit_notes,
                    updated_at = NOW()
            """, (
                data.parcel_id, data.village_id, data.survey_no, data.gat_no, data.cts_no,
                data.old_area, data.new_area, data.old_survey_year, data.old_survey_method,
                data.new_survey_method, data.audit_notes, datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
        return {"status": "success", "parcel_id": data.parcel_id}
    finally:
        conn.close()

@app.post("/api/parcels/modern-survey")
def modern_survey(data: ModernSurveyData):
    conn = get_db_connection()
    try:
        geom_json = None
        if data.points_text:
            lines = [l.strip() for l in data.points_text.split("\n") if l.strip()]
            coords = []
            for line in lines:
                parts = line.split(",")
                if len(parts) == 2:
                    try:
                        lat, lng = float(parts[0]), float(parts[1])
                        coords.append([lng, lat])
                    except ValueError:
                        pass
            if len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                geom_json = json.dumps({
                    "type": "Polygon",
                    "coordinates": [coords]
                })
            else:
                try:
                    parsed = json.loads(data.points_text)
                    geom_json = json.dumps({
                        "type": "Polygon",
                        "coordinates": parsed
                    })
                except Exception:
                    pass

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parcels SET
                    instrument_type = %s,
                    points_text = %s,
                    geom_json = %s,
                    accuracy_m = %s,
                    calculated_area = COALESCE(%s, calculated_area),
                    submitted_by = %s,
                    survey_timestamp = %s,
                    updated_at = %s
                WHERE parcel_id = %s
            """, (
                data.instrument_type, data.points_text, geom_json, data.accuracy_m,
                data.calculated_area, data.submitted_by, data.survey_timestamp,
                datetime.now(timezone.utc).isoformat(), data.parcel_id
            ))
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO parcels (
                        parcel_id, village_id, instrument_type, points_text, 
                        geom_json, accuracy_m, calculated_area, submitted_by, 
                        survey_timestamp, created_at
                    ) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.parcel_id, data.instrument_type, data.points_text, geom_json,
                    data.accuracy_m, data.calculated_area, data.submitted_by, data.survey_timestamp,
                    datetime.now(timezone.utc).isoformat()
                ))
            conn.commit()
        return {"status": "success", "parcel_id": data.parcel_id}
    finally:
        conn.close()

@app.post("/api/parcels/update-status")
def update_status(data: StatusUpdateData):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parcels SET
                    verification_status = %s,
                    updated_at = %s
                WHERE parcel_id = %s
            """, (data.verification_status, datetime.now(timezone.utc).isoformat(), data.parcel_id))
            conn.commit()
        return {"status": "success", "parcel_id": data.parcel_id}
    finally:
        conn.close()

@app.get("/api/parcels/list")
def list_parcels():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parcels")
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()

# ============================================================
# FRONTEND ROUTE
# ============================================================

@app.get("/")
def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>index.html not found! Please upload index.html to GitHub.</h1>", status_count=404)
