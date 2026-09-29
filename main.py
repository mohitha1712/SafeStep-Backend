from datetime import datetime, timezone
from typing import Optional
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DB_NAME = "safestep.db"

app = FastAPI(
    title="SafeStep API",
    description="Backend API for SafeStep Smart Cane",
    version="1.0.0",
)

# Allow the published Bolt frontend to communicate with the backend.
# During development, allow localhost as well.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://safestep-smart-cane-gsom.bolt.host",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SensorData(BaseModel):
    device: str = "SafeStep"
    distance_cm: float
    obstacle: bool
    moisture_raw: int
    moisture_percent: float
    surface: str
    risk_score: float
    ai_decision: str
    hazard: str
    wifi: str


class EventData(BaseModel):
    event_type: str
    description: Optional[str] = None
    hazard: Optional[str] = None


class ContactData(BaseModel):
    name: str
    relationship: str
    phone: str
    notification_preference: str = "high_risk"
    active: bool = True


def get_db():
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS sensor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device TEXT,
            distance_cm REAL,
            obstacle INTEGER,
            moisture_raw INTEGER,
            moisture_percent REAL,
            surface TEXT,
            risk_score REAL,
            ai_decision TEXT,
            hazard TEXT,
            wifi TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT,
            hazard TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relationship TEXT,
            phone TEXT,
            notification_preference TEXT,
            active INTEGER
        )
    """)

    db.commit()
    db.close()


init_db()

latest_sensor: Optional[dict] = None
last_seen: Optional[str] = None


@app.get("/")
def root():
    return {
        "name": "SafeStep API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "SafeStep API"
    }


@app.post("/api/safestep")
def receive_sensor_data(data: SensorData):
    global latest_sensor, last_seen

    timestamp = datetime.now(timezone.utc).isoformat()

    sensor = data.model_dump()
    sensor["timestamp"] = timestamp

    latest_sensor = sensor
    last_seen = timestamp

    db = get_db()

    db.execute("""
        INSERT INTO sensor_history (
            timestamp,
            device,
            distance_cm,
            obstacle,
            moisture_raw,
            moisture_percent,
            surface,
            risk_score,
            ai_decision,
            hazard,
            wifi
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        data.device,
        data.distance_cm,
        int(data.obstacle),
        data.moisture_raw,
        data.moisture_percent,
        data.surface,
        data.risk_score,
        data.ai_decision,
        data.hazard,
        data.wifi,
    ))

    db.commit()
    db.close()

    return {
        "success": True,
        "message": "Sensor data received",
        "timestamp": timestamp
    }


@app.get("/api/sensors/latest")
def get_latest_sensor():
    if latest_sensor is None:
        return {
            "status": "NO_DATA",
            "data": None
        }

    return {
        "status": "CONNECTED",
        "data": latest_sensor
    }


@app.get("/api/safety/current")
def get_current_safety():
    if latest_sensor is None:
        return {
            "status": "NO_DATA",
            "safety": None
        }

    return {
        "status": "AVAILABLE",
        "safety": {
            "risk_score": latest_sensor["risk_score"],
            "ai_decision": latest_sensor["ai_decision"],
            "hazard": latest_sensor["hazard"],
            "surface": latest_sensor["surface"],
            "obstacle": latest_sensor["obstacle"],
        }
    }


@app.get("/api/device")
def get_device():
    if latest_sensor is None:
        return {
            "device": "SafeStep",
            "status": "NO_DATA",
            "last_seen": None,
            "wifi": "UNKNOWN"
        }

    return {
        "device": latest_sensor["device"],
        "status": "CONNECTED",
        "last_seen": last_seen,
        "wifi": latest_sensor["wifi"]
    }


@app.get("/api/history")
def get_history(limit: int = 100):
    limit = max(1, min(limit, 1000))

    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM sensor_history
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    db.close()

    return {
        "count": len(rows),
        "data": [dict(row) for row in rows]
    }


@app.get("/api/contacts")
def get_contacts():
    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM contacts
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return {
        "count": len(rows),
        "data": [dict(row) for row in rows]
    }


@app.post("/api/events")
def create_event(event: EventData):
    timestamp = datetime.now(timezone.utc).isoformat()

    db = get_db()

    cursor = db.execute("""
        INSERT INTO events (
            timestamp,
            event_type,
            description,
            hazard
        )
        VALUES (?, ?, ?, ?)
    """, (
        timestamp,
        event.event_type,
        event.description,
        event.hazard,
    ))

    db.commit()
    event_id = cursor.lastrowid
    db.close()

    return {
        "success": True,
        "event_id": event_id,
        "timestamp": timestamp
    }


@app.post("/api/alerts/acknowledge")
def acknowledge_alert(event_id: int):
    db = get_db()

    exists = db.execute(
        "SELECT id FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()

    db.close()

    if exists is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    return {
        "success": True,
        "message": "Alert acknowledged",
        "event_id": event_id
    }


@app.post("/api/contacts")
def add_contact(contact: ContactData):
    db = get_db()

    cursor = db.execute("""
        INSERT INTO contacts (
            name,
            relationship,
            phone,
            notification_preference,
            active
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        contact.name,
        contact.relationship,
        contact.phone,
        contact.notification_preference,
        int(contact.active),
    ))

    db.commit()
    contact_id = cursor.lastrowid
    db.close()

    return {
        "success": True,
        "contact_id": contact_id
    }