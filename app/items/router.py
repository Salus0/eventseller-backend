import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMAS ---
class ItemCreate(BaseModel):
    item_id: int          # Ingame Item-ID (z.B. 1026)
    name: str             # z.B. Elunium
    image_url: str | None = None  # z.B. https://file5s.ratemyserver.net/items/small/1026.gif

# --- ITEM ANLEGEN ODER UPDATE (POST) ---
@router.post("/")
def create_or_update_item(item: ItemCreate):
    """Erstellt ein neues Item oder aktualisiert die Stammdaten anhand der item_id"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    
    # Automatische Bild-URL generieren, falls keine angegeben wurde
    img_url = item.image_url
    if not img_url and item.item_id:
        img_url = f"https://file5s.ratemyserver.net/items/small/{item.item_id}.gif"

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO items (ro_item_id, name, image_url) 
            VALUES (%s, %s, %s)
            ON CONFLICT (ro_item_id) DO UPDATE 
            SET name = EXCLUDED.name, image_url = EXCLUDED.image_url
            RETURNING *;
            """,
            (item.item_id, item.name, img_url)
        )
        saved_item = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return saved_item
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern des Items: {str(e)}")

# --- ALLE ITEMS ABFRAGEN INKL. LETZTEM PREIS (GET) ---
@router.get("/")
def get_items():
    """Holt alle Items inklusive des aktuellsten Verkaufspreises und Verkaufsdatums"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # Holt alle Items + den preislich neuesten Verkauf per Subquery/JOIN aus der Verkäufe-Tabelle
        query = """
            SELECT 
                i.item_id,
                i.name,
                i.image_url,
                last_sales.price AS last_price,
                last_sales.sold_at AS last_sold_at
            FROM items i
            LEFT JOIN LATERAL (
                SELECT s.price, s.created_at AS sold_at
                FROM sales s
                WHERE s.item_id = i.item_id AND s.price IS NOT NULL
                ORDER BY s.created_at DESC
                LIMIT 1
            ) last_sales ON TRUE
            ORDER BY i.name ASC;
        """
        cur.execute(query)
        items = cur.fetchall()
        cur.close()
        conn.close()
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Items: {str(e)}")

# --- ITEM-HISTORIE / DETAILS ABFRAGEN (GET) ---
@router.get("/{item_id}/history")
def get_item_history(item_id: int):
    """Holt alle Runs, in denen das Item verkauft wurde (Preisentwicklung)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        query = """
            SELECT 
                s.id AS sale_id,
                r.name AS run_name,
                r.created_at AS run_date,
                s.price,
                s.quantity
            FROM sales s
            JOIN runs r ON s.run_id = r.id
            WHERE s.item_id = %s
            ORDER BY r.created_at DESC;
        """
        cur.execute(query, (item_id,))
        history = cur.fetchall()
        cur.close()
        conn.close()
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Historie: {str(e)}")
