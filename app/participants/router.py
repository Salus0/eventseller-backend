import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMA FÜR PARTICIPANTS ---
class ParticipantCreate(BaseModel):
    name: str
    discord_id: str | None = None

# --- TEILNEHMER ANLEGEN (POST) ---
@router.post("/")
def create_participant(participant: ParticipantCreate):
    """Erstellt einen neuen Teilnehmer in der Datenbank"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO participants (name, discord_id) VALUES (%s, %s) RETURNING *;",
            (participant.name, participant.discord_id)
        )
        new_participant = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_participant
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern: {str(e)}")

# --- ALLE TEILNEHMER ABFRAGEN (GET) ---
@router.get("/")
def get_participants():
    """Ruft alle Teilnehmer aus der Datenbank ab"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM participants ORDER BY id ASC;")
        participants = cur.fetchall()
        cur.close()
        conn.close()
        return participants
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden: {str(e)}")
