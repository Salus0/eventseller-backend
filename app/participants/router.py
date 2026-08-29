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

# --- SCHEMA FÜR TEILNEHMER-UPDATE ---
class ParticipantUpdate(BaseModel):
    name: str
    discord_id: str | None = None

# --- TEILNEHMER BEARBEITEN (PUT) ---
@router.put("/{participant_id}")
def update_participant(participant_id: int, participant: ParticipantUpdate):
    """Aktualisiert einen bestehenden Teilnehmer in der Datenbank"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Prüfen, ob der Teilnehmer existiert
        cur.execute("SELECT * FROM participants WHERE id = %s;", (participant_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")

        # Update durchführen (discord_id direkt mit dem Wert aus der Anfrage überschreiben)
        cur.execute(
            """
            UPDATE participants 
            SET name = %s, discord_id = %s 
            WHERE id = %s 
            RETURNING *;
            """,
            (participant.name, participant.discord_id, participant_id)
        )
        updated_participant = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return updated_participant
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren: {str(e)}")