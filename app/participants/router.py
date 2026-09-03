import os
import jwt
from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel
from app.db.database import get_connection, release_connection

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-this")

# --- AUTH-DEPENDENCIES ---

def get_current_user(authorization: str = Header(None)):
    """Prüft, ob ein valider JWT-Token übergeben wurde (für alle eingeloggten Rollen)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht authentifiziert. Bitte logge dich ein."
        )
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Token."
        )

def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    """Stellt sicher, dass der angemeldete Nutzer die Admin-Rolle besitzt."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung! Nur Admins dürfen diese Aktion ausführen."
        )
    return current_user


# --- SCHEMA FÜR PARTICIPANTS ---
class ParticipantCreate(BaseModel):
    name: str
    discord_id: str | None = None

class ParticipantUpdate(BaseModel):
    name: str
    discord_id: str | None = None


# --- TEILNEHMER ANLEGEN (POST) - Nur für Admins ---
@router.post("/")
def create_participant(
    participant: ParticipantCreate,
    admin_user: dict = Depends(get_current_admin_user)
):
    """Erstellt einen neuen Teilnehmer in der Datenbank (Nur Admins)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO participants (name, discord_id) VALUES (%s, %s) RETURNING *;",
            (participant.name, participant.discord_id)
        )
        new_participant = cur.fetchone()
        conn.commit()
        cur.close()
        release_connection(conn)
        return new_participant
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern: {str(e)}")


# --- ALLE TEILNEHMER ABFRAGEN (GET) - Für alle eingeloggten Nutzer ---
@router.get("/")
def get_participants(current_user: dict = Depends(get_current_user)):
    """Ruft alle Teilnehmer aus der Datenbank ab (Nur angemeldete Nutzer)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM participants ORDER BY id ASC;")
        participants = cur.fetchall()
        cur.close()
        release_connection(conn)
        return participants
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden: {str(e)}")


# --- TEILNEHMER BEARBEITEN (PUT) - Nur für Admins ---
@router.put("/{participant_id}")
def update_participant(
    participant_id: int,
    participant: ParticipantUpdate,
    admin_user: dict = Depends(get_current_admin_user)
):
    """Aktualisiert einen bestehenden Teilnehmer in der Datenbank (Nur Admins)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Prüfen, ob der Teilnehmer existiert
        cur.execute("SELECT * FROM participants WHERE id = %s;", (participant_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            release_connection(conn)
            raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")

        # Update durchführen
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
        release_connection(conn)

        return updated_participant
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren: {str(e)}")