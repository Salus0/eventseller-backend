import os
import jwt
from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor

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

def get_current_seller_or_admin_user(current_user: dict = Depends(get_current_user)):
    """Stellt sicher, dass der angemeldete Nutzer mindestens Seller oder Admin ist."""
    user_role = current_user.get("role")
    if user_role not in ["seller", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung! Nur Seller und Admins dürfen diese Aktion ausführen."
        )
    return current_user


# --- SCHEMAS ---
class ParticipantCreate(BaseModel):
    name: str
    discord_id: str | None = None
    role: str | None = "user"

class ParticipantUpdate(BaseModel):
    name: str
    discord_id: str | None = None
    role: str | None = "user"

class CharacterCreate(BaseModel):
    account_number: str
    class_name: str
    build_name: str
    name: Optional[str] = None


# --- TEILNEHMER ANLEGEN (POST) - Für Admins UND Seller ---
@router.post("/")
def create_participant(
    participant: ParticipantCreate,
    current_user: dict = Depends(get_current_seller_or_admin_user)
):
    """Erstellt einen neuen Teilnehmer in der Datenbank (Admins & Seller)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO participants (name, discord_id, role) VALUES (%s, %s, %s) RETURNING *;",
            (participant.name, participant.discord_id, participant.role or "user")
        )
        new_participant = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
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
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM participants ORDER BY id ASC;")
        participants = cur.fetchall()
        cur.close()
        conn.close()
        return participants
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden: {str(e)}")


# --- EINZELNEN TEILNEHMER ABFRAGEN (GET) - Für die Detailseite ---
@router.get("/{participant_id}")
def get_participant(participant_id: int, current_user: dict = Depends(get_current_user)):
    """Ruft einen einzelnen Teilnehmer anhand seiner ID ab"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM participants WHERE id = %s;", (participant_id,))
        participant = cur.fetchone()
        cur.close()
        conn.close()

        if not participant:
            raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")
        return participant
    except HTTPException:
        raise
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
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Prüfen, ob der Teilnehmer existiert
        cur.execute("SELECT * FROM participants WHERE id = %s;", (participant_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")

        # Update durchführen
        cur.execute(
            """
            UPDATE participants 
            SET name = %s, discord_id = %s, role = %s
            WHERE id = %s 
            RETURNING *;
            """,
            (participant.name, participant.discord_id, participant.role or "user", participant_id)
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


# --- CHARAKTERE EINES TEILNEHMERS ABRUFEN (GET) ---
@router.get("/{participant_id}/characters")
def get_participant_characters(participant_id: int, current_user: dict = Depends(get_current_user)):
    """Ruft alle Charaktere eines bestimmten Teilnehmers ab"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM characters WHERE participant_id = %s ORDER BY id ASC;", (participant_id,))
        characters = cur.fetchall()
        cur.close()
        conn.close()
        return characters
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Charaktere: {str(e)}")


# --- NEUEN CHARAKTER HINZUFÜGEN (POST) ---
@router.post("/{participant_id}/characters")
def add_character(
    participant_id: int,
    char: CharacterCreate,
    current_user: dict = Depends(get_current_user)
):
    """Fügt einem Teilnehmer einen neuen Charakter hinzu"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Prüfen ob Teilnehmer existiert
        cur.execute("SELECT id FROM participants WHERE id = %s;", (participant_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Teilnehmer nicht gefunden")

        cur.execute(
            """
            INSERT INTO characters (participant_id, account_number, class_name, build_name, name) 
            VALUES (%s, %s, %s, %s, %s) 
            RETURNING *;
            """,
            (participant_id, char.account_number, char.class_name, char.build_name, char.name)
        )
        new_char = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_char
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern des Charakters: {str(e)}")


# --- CHARAKTER LÖSCHEN (DELETE) ---
@router.delete("/{participant_id}/characters/{char_id}")
def delete_character(
    participant_id: int,
    char_id: int,
    admin_user: dict = Depends(get_current_admin_user)
):
    """Löscht einen Charakter (Nur Admins)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("DELETE FROM characters WHERE id = %s AND participant_id = %s RETURNING id;", (char_id, participant_id))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="Charakter nicht gefunden")

        return {"message": "Charakter erfolgreich gelöscht"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")


# --- AUSZAHLUNGEN FÜR DIE STATISTIK / HISTORIE (GET) ---
@router.get("/{participant_id}/payouts")
def get_participant_payouts(participant_id: int, current_user: dict = Depends(get_current_user)):
    """Ruft alle ausgezahlten Runs des Teilnehmers ab (für die Historie & Statistik)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT rp.run_id, r.name AS run_name, r.created_at, rp.payout_amount, rp.is_paid
            FROM run_participants rp
            JOIN runs r ON rp.run_id = r.id
            WHERE rp.participant_id = %s AND rp.is_paid = TRUE;
            """,
            (participant_id,)
        )
        results = cur.fetchall()
        cur.close()
        conn.close()

        payout_list = []
        for row in results:
            payout_list.append({
                "run_id": row["run_id"],
                "run_name": row["run_name"],
                "date": row["created_at"].strftime("%d.%m.%Y") if row["created_at"] else None,
                "payout_amount": row["payout_amount"],
                "is_paid": row["is_paid"]
            })
        return payout_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Auszahlungen: {str(e)}")