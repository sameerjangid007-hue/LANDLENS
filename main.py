import os
import json
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# ============================================================
# LANDLENS
# FastAPI + PostgreSQL
# Render compatible
# No login/authentication at this stage
# ============================================================

app = FastAPI(
    title="LANDLENS Land Survey & Verification Platform",
    version="2.0.0"
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
    """
    Create PostgreSQL connection.
    Render provides DATABASE_URL through environment variables.
    """

    if not DATABASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL is not configured on the server."
        )

    try:
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )

    except psycopg2.Error as e:
        print("DATABASE CONNECTION ERROR:", str(e))

        raise HTTPException(
            status_code=503,
            detail="Database connection failed. Check Render DATABASE_URL."
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

            # ------------------------------------------------
            # Main parcel table
            # ------------------------------------------------

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

                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ------------------------------------------------
            # Existing databases
            # Add missing columns safely
            # ------------------------------------------------

            columns = {

                "survey_no": "TEXT",
                "gat_no": "TEXT",
                "cts_no": "TEXT",

                "reference_ror": "TEXT",

                "old_area": "REAL DEFAULT 0",
                "new_area": "REAL DEFAULT 0",

                "old_survey_year": "INTEGER",
                "old_survey_method": "TEXT",
                "new_survey_method": "TEXT",

                "old_north": "REAL",
                "old_south": "REAL",
                "old_east": "REAL",
                "old_west": "REAL",

                "points_text": "TEXT",
                "geom_json": "TEXT",

                "instrument_type": "TEXT",
                "accuracy_m": "REAL",
                "calculated_area": "REAL",

                "submitted_by": "TEXT",
                "survey_timestamp": "TEXT",

                "quality_status": "TEXT DEFAULT 'REVIEW REQUIRED'",

                "ai_risk_score": "REAL DEFAULT 0",
                "ai_risk_type": "TEXT",

                "verification_status": "TEXT DEFAULT 'PENDING'",

                "audit_notes": "TEXT",

                "created_at": "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP"
            }

            for column, definition in columns.items():

                cur.execute(
                    f"""
                    ALTER TABLE parcels
                    ADD COLUMN IF NOT EXISTS {column} {definition}
                    """
                )

            conn.commit()

        print("LANDLENS DATABASE INITIALIZED SUCCESSFULLY.")

    except Exception as e:

        if conn:
            conn.rollback()

        print("DATABASE INITIALIZATION ERROR:", str(e))

    finally:

        if conn:
            conn.close()


init_db()


# ============================================================
# PYDANTIC MODELS
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

    points_text: str = ""

    accuracy_m: float | None = None

    calculated_area: float | None = None

    submitted_by: str | None = None

    survey_timestamp: str | None = None


class StatusUpdateData(BaseModel):

    parcel_id: str

    verification_status: str

    reviewer_role: str | None = None


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health_check():

    if not DATABASE_URL:

        return {
            "status": "error",
            "database": "not_configured",
            "message": "DATABASE_URL is missing."
        }

    conn = None

    try:

        conn = get_db_connection()

        with conn.cursor() as cur:

            cur.execute("SELECT NOW() AS server_time")

            result = cur.fetchone()

        return {
            "status": "ok",
            "database": "connected",
            "server_time": result["server_time"]
        }

    except Exception as e:

        print("HEALTH CHECK ERROR:", str(e))

        return {
            "status": "error",
            "database": "connection_failed",
            "message": str(e)
        }

    finally:

        if conn:
            conn.close()


# ============================================================
# REGISTER / CREATE PARCEL
# ============================================================

@app.post("/api/parcels/register")
def register_parcel(data: RegisterData):

    conn = get_db_connection()

    try:

        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO parcels (
                    parcel_id,
                    village_id,
                    survey_no,
                    gat_no,
                    cts_no,
                    old_area,
                    new_area,
                    old_survey_year,
                    old_survey_method,
                    new_survey_method,
                    audit_notes,
                    verification_status,
                    created_at,
                    updated_at
                )

                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, 'PENDING', %s, %s
                )

                ON CONFLICT (parcel_id)
                DO UPDATE SET

                    village_id = EXCLUDED.village_id,

                    survey_no = EXCLUDED.survey_no,

                    gat_no = EXCLUDED.gat_no,

                    cts_no = EXCLUDED.cts_no,

                    old_area = EXCLUDED.old_area,

                    new_area = EXCLUDED.new_area,

                    old_survey_year =
                        EXCLUDED.old_survey_year,

                    old_survey_method =
                        EXCLUDED.old_survey_method,

                    new_survey_method =
                        EXCLUDED.new_survey_method,

                    audit_notes =
                        EXCLUDED.audit_notes,

                    updated_at = EXCLUDED.updated_at
                """,

                (
                    data.parcel_id,
                    data.village_id,
                    data.survey_no,
                    data.gat_no,
                    data.cts_no,
                    data.old_area,
                    data.new_area,
                    data.old_survey_year,
                    data.old_survey_method,
                    data.new_survey_method,
                    data.audit_notes,
                    now,
                    now
                )
            )

        conn.commit()

        return {
            "status": "success",
            "message": "Parcel saved successfully.",
            "parcel_id": data.parcel_id
        }

    except psycopg2.Error as e:

        conn.rollback()

        print("REGISTER PARCEL ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not save parcel: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# SAVE OLD RECORD
# ============================================================

@app.post("/api/parcels/old-record")
def save_old_record(data: OldRecordData):

    conn = get_db_connection()

    try:

        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE parcels

                SET
                    reference_ror = %s,

                    old_survey_year =
                        COALESCE(%s, old_survey_year),

                    old_survey_method =
                        COALESCE(%s, old_survey_method),

                    old_north =
                        COALESCE(%s, old_north),

                    old_south =
                        COALESCE(%s, old_south),

                    old_east =
                        COALESCE(%s, old_east),

                    old_west =
                        COALESCE(%s, old_west),

                    updated_at = %s

                WHERE parcel_id = %s
                """,

                (
                    data.reference_ror,
                    data.old_survey_year,
                    data.old_method,
                    data.north_dim,
                    data.south_dim,
                    data.east_dim,
                    data.west_dim,
                    now,
                    data.parcel_id
                )
            )

            if cur.rowcount == 0:

                cur.execute(
                    """
                    INSERT INTO parcels (
                        parcel_id,
                        village_id,
                        reference_ror,
                        old_survey_year,
                        old_survey_method,
                        old_north,
                        old_south,
                        old_east,
                        old_west,
                        verification_status,
                        created_at,
                        updated_at
                    )

                    VALUES (
                        %s,
                        1,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        'PENDING',
                        %s,
                        %s
                    )
                    """,

                    (
                        data.parcel_id,
                        data.reference_ror,
                        data.old_survey_year,
                        data.old_method,
                        data.north_dim,
                        data.south_dim,
                        data.east_dim,
                        data.west_dim,
                        now,
                        now
                    )
                )

        conn.commit()

        return {
            "status": "success",
            "message": "Old record saved successfully.",
            "parcel_id": data.parcel_id
        }

    except psycopg2.Error as e:

        conn.rollback()

        print("OLD RECORD ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not save old record: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# SAVE MODERN SURVEY
# ============================================================

@app.post("/api/parcels/modern-survey")
def modern_survey(data: ModernSurveyData):

    conn = get_db_connection()

    try:

        geom_json = None

        # ----------------------------------------------------
        # Convert latitude,longitude text into GeoJSON polygon
        # ----------------------------------------------------

        if data.points_text:

            lines = [
                line.strip()
                for line in data.points_text.splitlines()
                if line.strip()
            ]

            coords = []

            for line in lines:

                parts = [
                    x.strip()
                    for x in line.split(",")
                ]

                if len(parts) == 2:

                    try:

                        lat = float(parts[0])
                        lng = float(parts[1])

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

                    if isinstance(parsed, dict):

                        geom_json = json.dumps(parsed)

                    else:

                        geom_json = json.dumps({
                            "type": "Polygon",
                            "coordinates": parsed
                        })

                except Exception:

                    geom_json = None

        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE parcels

                SET
                    instrument_type = %s,

                    points_text = %s,

                    geom_json = %s,

                    accuracy_m = %s,

                    calculated_area =
                        COALESCE(%s, calculated_area),

                    submitted_by = %s,

                    survey_timestamp = %s,

                    updated_at = %s

                WHERE parcel_id = %s
                """,

                (
                    data.instrument_type,
                    data.points_text,
                    geom_json,
                    data.accuracy_m,
                    data.calculated_area,
                    data.submitted_by,
                    data.survey_timestamp,
                    now,
                    data.parcel_id
                )
            )

            # If parcel doesn't exist, create it.
            if cur.rowcount == 0:

                cur.execute(
                    """
                    INSERT INTO parcels (
                        parcel_id,
                        village_id,
                        instrument_type,
                        points_text,
                        geom_json,
                        accuracy_m,
                        calculated_area,
                        submitted_by,
                        survey_timestamp,
                        verification_status,
                        created_at,
                        updated_at
                    )

                    VALUES (
                        %s,
                        1,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        'PENDING',
                        %s,
                        %s
                    )
                    """,

                    (
                        data.parcel_id,
                        data.instrument_type,
                        data.points_text,
                        geom_json,
                        data.accuracy_m,
                        data.calculated_area,
                        data.submitted_by,
                        data.survey_timestamp,
                        now,
                        now
                    )
                )

        conn.commit()

        return {
            "status": "success",
            "message": "Modern survey saved successfully.",
            "parcel_id": data.parcel_id
        }

    except psycopg2.Error as e:

        conn.rollback()

        print("MODERN SURVEY ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not save modern survey: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# UPDATE VERIFICATION STATUS
# ============================================================

@app.post("/api/parcels/update-status")
def update_status(data: StatusUpdateData):

    allowed_statuses = {
        "PENDING",
        "UNDER REVIEW",
        "VERIFIED",
        "APPROVED",
        "REJECTED",
        "RESURVEY REQUIRED"
    }

    if data.verification_status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail="Invalid verification status."
        )

    conn = get_db_connection()

    try:

        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE parcels

                SET
                    verification_status = %s,
                    updated_at = %s

                WHERE parcel_id = %s
                """,

                (
                    data.verification_status,
                    now,
                    data.parcel_id
                )
            )

            if cur.rowcount == 0:

                raise HTTPException(
                    status_code=404,
                    detail="Parcel not found."
                )

        conn.commit()

        return {
            "status": "success",
            "message": "Parcel status updated.",
            "parcel_id": data.parcel_id,
            "verification_status": data.verification_status
        }

    except HTTPException:

        conn.rollback()
        raise

    except psycopg2.Error as e:

        conn.rollback()

        print("STATUS UPDATE ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not update status: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# LIST ALL PARCELS
# ============================================================

@app.get("/api/parcels/list")
def list_parcels():

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM parcels
                ORDER BY updated_at DESC NULLS LAST
                """
            )

            rows = cur.fetchall()

        return rows

    except psycopg2.Error as e:

        print("LIST PARCELS ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not load parcels: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# GET ONE PARCEL
# ============================================================

@app.get("/api/parcels/get/{parcel_id}")
def get_parcel(parcel_id: str):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM parcels
                WHERE parcel_id = %s
                """,
                (parcel_id,)
            )

            row = cur.fetchone()

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Parcel not found."
            )

        return row

    except HTTPException:
        raise

    except psycopg2.Error as e:

        print("GET PARCEL ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not load parcel: {str(e)}"
        )

    finally:

        conn.close()


# ============================================================
# ROOT / FRONTEND
# ============================================================

@app.get("/")
def read_root():

    try:

        with open(
            "index.html",
            "r",
            encoding="utf-8"
        ) as f:

            html = f.read()

        return HTMLResponse(
            content=html,
            status_code=200
        )

    except FileNotFoundError:

        return HTMLResponse(
            content="""
            <html>
            <body>
                <h1>LANDLENS</h1>
                <p>index.html not found.</p>
            </body>
            </html>
            """,
            status_code=404
        )


# ============================================================
# STARTUP MESSAGE
# ============================================================

@app.on_event("startup")
def startup_event():

    print("--------------------------------------------")
    print("LANDLENS SERVER STARTED")
    print("Database configured:", bool(DATABASE_URL))
    print("Authentication: DISABLED")
    print("Roles:")
    print(" - FARMER")
    print(" - SURVEYOR")
    print(" - OFFICER")
    print(" - ADMIN")
    print("--------------------------------------------")
