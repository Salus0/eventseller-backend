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
        img_url = item.image_url if item.image_url else f"/items/{item.item_id}.png"

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

# --- ALLE ITEMS ABFRAGEN (GET) ---
@router.get("/")
def get_items():
    """Holt alle Items aus der Datenbank"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        query = """
            SELECT 
                i.id,
                i.ro_item_id AS item_id,
                i.name,
                i.image_url,
                COALESCE(i.default_price, 0) AS default_price,
                last_sales.actual_price AS last_price,
                NULL AS last_sold_at
            FROM items i
            LEFT JOIN LATERAL (
                SELECT s.actual_price
                FROM sales s
                WHERE s.item_id = i.ro_item_id OR s.item_id = i.id
                ORDER BY s.id DESC
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
        print(f"CRITICAL ERROR IN GET /items: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Datenbank-Fehler: {str(e)}")


# --- ITEM-HISTORIE / DETAILS ABFRAGEN (GET) ---
@router.get("/{item_id}/history")
def get_item_history(item_id: int):
    """Holt alle Runs, in denen das Item verkauft wurde"""
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
                s.actual_price AS price,
                s.quantity,
                s.buyer_name
            FROM sales s
            JOIN runs r ON s.run_id = r.id
            WHERE s.item_id = %s OR s.item_id = (SELECT id FROM items WHERE ro_item_id = %s LIMIT 1)
            ORDER BY r.created_at DESC;
        """
        cur.execute(query, (item_id, item_id))
        history = cur.fetchall()
        cur.close()
        conn.close()
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Historie: {str(e)}")

# --- SCHEMA FÜR ITEM-UPDATE ---
class ItemUpdate(BaseModel):
    item_id: int
    name: str
    image_url: str | None = None

# --- ITEM BEARBEITEN (PUT) ---
@router.put("/{id}")
def update_item(id: int, item: ItemUpdate):
    """Aktualisiert die Stammdaten eines Items anhand der internen Daten-ID"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    img_url = item.image_url
    if not img_url and item.item_id:
        img_url = f"https://file5s.ratemyserver.net/items/small/{item.item_id}.gif"

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Prüfen, ob das Item existiert
        cur.execute("SELECT * FROM items WHERE id = %s;", (id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Item nicht gefunden")

        cur.execute(
            """
            UPDATE items 
            SET ro_item_id = %s, name = %s, image_url = %s 
            WHERE id = %s 
            RETURNING *;
            """,
            (item.item_id, item.name, img_url, id)
        )
        updated_item = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren: {str(e)}")
