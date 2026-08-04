import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMAS ---
class RunCreate(BaseModel):
    name: str  # z. B. "Geffen Tower Run"

class SaleCreate(BaseModel):
    item_id: int
    quantity: int = 1
    actual_price: int  # Tatsächlicher Verkaufspreis für diesen Run
    buyer_name: str | None = None  # Optional: Name des Käufers

# --- RUN ERSTELLEN (POST) ---
@router.post("/")
def create_run(run: RunCreate):
    """Erstellt einen neuen Event-Run"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO runs (name) VALUES (%s) RETURNING *;",
            (run.name,)
        )
        new_run = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_run
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern des Runs: {str(e)}")

# --- ALLE RUNS ABFRAGEN (GET) ---
@router.get("/")
def get_runs():
    """Ruft alle Event-Runs ab"""
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
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Runs: {str(e)}")

# --- VERKAUF ZU EINEM RUN HINZUFÜGEN (POST) ---
@router.post("/{run_id}/sales")
def create_sale(run_id: int, sale: SaleCreate):
    """Fügt einen Verkaufs-Eintrag zu einem spezifischen Run hinzu"""
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
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern des Verkaufs: {str(e)}")

# --- VERKÄUFE EINES RUNS ABFRAGEN (GET) ---
@router.get("/{run_id}/sales")
def get_run_sales(run_id: int):
    """Ruft alle Verkäufe eines spezifischen Runs ab (inkl. Item-Namen)"""
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
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Verkäufe: {str(e)}")
