import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMA FÜR DAS ANLEGEN EINES ITEMS ---
class ItemCreate(BaseModel):
    name: str
    default_price: int = 0

# --- ITEM ANLEGEN (POST) ---
@router.post("/")
def create_item(item: ItemCreate):
    """Erstellt ein neues Item in der Datenbank"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (name, default_price) VALUES (%s, %s) RETURNING *;",
            (item.name, item.default_price)
        )
        new_item = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_item
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern: {str(e)}")

# --- ALLE ITEMS ABFRAGEN (GET) ---
@router.get("/")
def get_items():
    """Ruft alle Items aus der Datenbank ab"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT * FROM items ORDER BY id ASC;")
        items = cur.fetchall()
        cur.close()
        conn.close()
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden: {str(e)}")
