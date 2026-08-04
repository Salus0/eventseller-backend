import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMAS ---
class RunCreate(BaseModel):
    name: str

class SaleCreate(BaseModel):
    item_id: int
    quantity: int = 1
    actual_price: int
    buyer_name: str | None = None

class RunParticipantAdd(BaseModel):
    participant_id: int

# --- RUN ERSTELLEN (POST) ---
@router.post("/")
def create_run(run: RunCreate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("INSERT INTO runs (name) VALUES (%s) RETURNING *;", (run.name,))
        new_run = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_run
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

# --- ALLE RUNS ABFRAGEN (GET) ---
@router.get("/")
def get_runs():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM runs ORDER BY id DESC;")
        runs = cur.fetchall()
        cur.close()
        conn.close()
        return runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

# --- VERKAUF ZU RUN HINZUFÜGEN (POST) ---
@router.post("/{run_id}/sales")
def create_sale(run_id: int, sale: SaleCreate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sales (run_id, item_id, quantity, actual_price, buyer_name)
            VALUES (%s, %s, %s, %s, %s) RETURNING *;
            """,
            (run_id, sale.item_id, sale.quantity, sale.actual_price, sale.buyer_name)
        )
        new_sale = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_sale
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

# --- VERKÄUFE EINES RUNS ABFRAGEN (GET) ---
@router.get("/{run_id}/sales")
def get_run_sales(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.*, i.name as item_name, i.ro_item_id
            FROM sales s
            LEFT JOIN items i ON s.item_id = i.id
            WHERE s.run_id = %s
            ORDER BY s.id ASC;
            """,
            (run_id,)
        )
        sales = cur.fetchall()
        cur.close()
        conn.close()
        return sales
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

# --- TEILNEHMER ZUM RUN HINZUFÜGEN (POST) ---
@router.post("/{run_id}/participants")
def add_participant_to_run(run_id: int, entry: RunParticipantAdd):
    """Verknüpft einen bestehenden Teilnehmer mit diesem Run"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_participants (run_id, participant_id) VALUES (%s, %s) RETURNING *;",
            (run_id, entry.participant_id)
        )
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Hinzufügen des Teilnehmers: {str(e)}")

# --- TEILNEHMER EINES RUNS ABFRAGEN (GET) ---
@router.get("/{run_id}/participants")
def get_run_participants(run_id: int):
    """Lädt alle Spieler, die an diesem Run teilgenommen haben"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.* FROM run_participants rp
            JOIN participants p ON rp.participant_id = p.id
            WHERE rp.run_id = %s;
            """,
            (run_id,)
        )
        participants = cur.fetchall()
        cur.close()
        conn.close()
        return participants
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden: {str(e)}")

# --- ZENY-SPLIT & ZUSAMMENFASSUNG BERECHNEN (GET) ---
@router.get("/{run_id}/summary")
def get_run_summary(run_id: int):
    """Berechnet Gesamteinnahmen, Teilnehmerzahl und Zeny-Payout pro Spieler"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # 1. Gesamteinnahmen berechnen
        cur.execute("SELECT COALESCE(SUM(quantity * actual_price), 0) as total_zeny FROM sales WHERE run_id = %s;", (run_id,))
        total_zeny = cur.fetchone()["total_zeny"]
        
        # 2. Anzahl Teilnehmer ermitteln
        cur.execute("SELECT COUNT(*) as count FROM run_participants WHERE run_id = %s;", (run_id,))
        participant_count = cur.fetchone()["count"]
        
        # 3. Cut pro Spieler berechnen
        payout_per_player = int(total_zeny / participant_count) if participant_count > 0 else 0
        
        cur.close()
        conn.close()
        
        return {
            "run_id": run_id,
            "total_zeny": total_zeny,
            "participant_count": participant_count,
            "payout_per_player": payout_per_player
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei der Berechnung: {str(e)}")
