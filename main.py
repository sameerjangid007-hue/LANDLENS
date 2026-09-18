from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import json

# 1. Initialize the App First
app = FastAPI(title="LANDLENS API (SIH26010)")

# 2. Add the Root Route to serve the frontend over Ngrok
@app.get("/")
async def read_index():
    return FileResponse("index.html")

# 3. Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- IN-MEMORY DATABASE (Perfect for Hackathon Demos) ---
# Pre-loaded with one sample record so the dashboard isn't completely empty!
parcels_db = [
    {
        "parcel_id": "PIM-100",
        "village_id": 1,
        "old_area": 2500.0,
        "new_area": 2400.0,
        "area_difference": 100.0,
        "ai_risk_score": 15,
        "ai_risk_type": "Low Risk",
        "verification_status": "Approved by GOV-OFFICER",
        "reference_ror": "ROR-712-A45",
        "old_survey_year": 1984,
        "geom_json": '{"type": "Polygon", "coordinates": [[[74.7754, 20.9047], [74.7759, 20.9047], [74.7759, 20.9052], [74.7754, 20.9052], [74.7754, 20.9047]]]}'
    }
]

# --- DATA MODELS ---
class ParcelRegister(BaseModel):
    parcel_id: str
    village_id: int
    old_area: float
    new_area: float

class OldRecord(BaseModel):
    parcel_id: str
    old_survey_no: str
    old_survey_year: int
    old_method: str
    north_dim: float
    south_dim: float
    east_dim: float
    west_dim: float
    source_department: str
    reference_ror: str

class ModernSurvey(BaseModel):
    parcel_id: str
    instrument_type: str
    points_text: str

class UpdateStatus(BaseModel):
    parcel_id: str
    verification_status: str

# --- API ENDPOINTS ---

@app.get("/api/parcels/list")
async def list_parcels():
    return parcels_db

@app.post("/api/parcels/register")
async def register_parcel(data: ParcelRegister):
    diff = abs(data.old_area - data.new_area)
    diff_percent = (diff / data.old_area) * 100 if data.old_area > 0 else 0
    
    # Simple AI Risk Logic
    risk_score = int(diff_percent * 5)
    risk_type = "High Risk" if risk_score > 50 else "Low Risk"

    # Check if exists to update, else append
    existing = next((p for p in parcels_db if p["parcel_id"] == data.parcel_id), None)
    if existing:
        existing.update({"old_area": data.old_area, "new_area": data.new_area, "area_difference": round(diff, 2), "ai_risk_score": risk_score, "ai_risk_type": risk_type})
    else:
        parcels_db.append({
            "parcel_id": data.parcel_id, "village_id": data.village_id,
            "old_area": data.old_area, "new_area": data.new_area, "area_difference": round(diff, 2),
            "ai_risk_score": risk_score, "ai_risk_type": risk_type, "verification_status": "Pending Verification",
            "geom_json": None, "reference_ror": "N/A", "old_survey_year": "N/A"
        })
    return {"parcel_id": data.parcel_id, "area_difference": round(diff, 2), "area_difference_percent": round(diff_percent, 2), "risk_classification": risk_type}

@app.post("/api/parcels/old-record")
async def add_old_record(data: OldRecord):
    existing = next((p for p in parcels_db if p["parcel_id"] == data.parcel_id), None)
    if existing:
        existing["reference_ror"] = data.reference_ror
        existing["old_survey_year"] = data.old_survey_year
    return {"status": "success"}

@app.post("/api/parcels/modern-survey")
async def add_modern_survey(data: ModernSurvey):
    existing = next((p for p in parcels_db if p["parcel_id"] == data.parcel_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Parcel not registered first.")
    
    # Convert lat,lng string to GeoJSON format
    try:
        points = data.points_text.split(";")
        coords = []
        for pt in points:
            if pt.strip():
                lat, lng = map(float, pt.split(","))
                coords.append([lng, lat]) # GeoJSON is [Lng, Lat]
        if coords:
            if coords[0] != coords[-1]:
                coords.append(coords[0]) # Close polygon
            existing["geom_json"] = json.dumps({"type": "Polygon", "coordinates": [coords]})
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid coordinate format")
    
    return {"status": "success", "parcel_id": data.parcel_id}

@app.post("/api/parcels/update-status")
async def update_status(data: UpdateStatus):
    existing = next((p for p in parcels_db if p["parcel_id"] == data.parcel_id), None)
    if existing:
        existing["verification_status"] = data.verification_status
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Parcel not found")

@app.delete("/api/parcels/delete/{parcel_id}")
async def delete_parcel(parcel_id: str):
    global parcels_db
    parcels_db = [p for p in parcels_db if p["parcel_id"] != parcel_id]
    return {"status": "deleted"}