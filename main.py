import os
import json
import secrets
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, HTTPException, Request
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

            # ------------------------------------------------
            # Upgrade an already existing parcels table
            # ------------------------------------------------

            columns = [
                ("survey_no", "TEXT"),
                ("gat_no", "TEXT"),
                ("cts_no", "TEXT"),
                ("reference_ror", "TEXT"),

                ("old_survey_year", "INTEGER"),
                ("old_survey_method", "TEXT"),
                ("new_survey_method", "TEXT"),

                ("old_north", "REAL"),
                ("old_south", "REAL"),
                ("old_east", "REAL"),
                ("old_west", "REAL"),

                ("points_text", "TEXT"),
                ("geom_json", "TEXT"),

                ("instrument_type", "TEXT"),
                ("accuracy_m", "REAL"),
                ("calculated_area", "REAL"),

                ("submitted_by", "TEXT"),
                ("survey_timestamp", "TEXT"),

                ("quality_status", "TEXT"),
                ("ai_risk_score", "REAL"),
                ("ai_risk_type", "TEXT"),

                ("verification_status", "TEXT"),
                ("audit_notes", "TEXT"),

                ("created_at", "TEXT"),
                ("updated_at", "TEXT")
            ]

            for column_name, column_type in columns:
                cur.execute(
                    f"""
                    ALTER TABLE parcels
                    ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                    """
                )

            # ------------------------------------------------
            # Set defaults for existing records
            # ------------------------------------------------

            cur.execute("""
                UPDATE parcels
                SET verification_status = 'PENDING'
                WHERE verification_status IS NULL
            """)

            cur.execute("""
                UPDATE parcels
                SET quality_status = 'REVIEW REQUIRED'
                WHERE quality_status IS NULL
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
#
# These are DEVELOPMENT credentials.
#
# Surveyor:
# GOV-SURV / surveyor / pass123
#
# Survey Head:
# GOV-HEAD / surveyhead / pass123
#
# Officer:
# GOV-OFFICER / officer / pass123
#
# Admin:
# GOV-ADMIN / admin / admin123
#
# Farmer uses the prototype citizen flow in index.html.
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


# Temporary demo token store
ACTIVE_TOKENS = {}


# ============================================================
# Pydantic Models
# ============================================================

class RegisterData(BaseModel):

    parcel_id: str
    village_id: int

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