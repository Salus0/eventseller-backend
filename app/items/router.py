import os
import jwt
from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-this")

# --- AUTH-DEPENDENCIES ---

def get_current_user(authorization: str = Header(None)):
    """Prüft, ob ein valider JWT-Token übergeben wurde (für alle eingeloggten Nutzer)."""
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


# --- SCHEMAS ---
class ItemCreate(BaseModel):
    item_id: int          # Ingame Item-ID (z.B. 1026)
    name: str             # z.B. Elunium
    image_url: str | None = None  # z.B. https://file5s.ratemyserver.net/items/small/1026.gif

class ItemUpdate(BaseModel):
    item_id: int
    name: str
    image_url: str | None = None


# --- ITEM ANLEGEN ODER UPDATE (POST) - Nur für Admins ---
@router.post("/")
def create_or_update_item(
    item: ItemCreate,
    admin_user: dict = Depends(get_current_admin_user)
):
    """Erstellt ein neues Item oder aktualisiert die Stammdaten anhand der item_id (Nur Admins)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    
    img_url = item.image_url
    if not img_url and item.item_id:
        img_url = f"/items/{item.item_id}.png"

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


# --- ALLE ITEMS ABFRAGEN (GET) - Für alle eingeloggten Nutzer ---
@router.get("/")
def get_items(current_user: dict = Depends(get_current_user)):
    """Holt alle Items aus der Datenbank inklusive letztem Verkaufsdatum (Nur angemeldete Nutzer)"""
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
                last_sales.sold_at AS last_sold_at
            FROM items i
            LEFT JOIN LATERAL (
                SELECT s.actual_price, s.sold_at
                FROM sales s
                WHERE s.item_id = i.ro_item_id OR s.item_id = i.id
                ORDER BY s.sold_at DESC NULLS LAST, s.id DESC
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


# --- ITEM-HISTORIE / DETAILS ABFRAGEN (GET) - Für alle eingeloggten Nutzer ---
@router.get("/{item_id}/history")
def get_item_history(
    item_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Holt alle Runs, in denen das Item verkauft wurde (Nur angemeldete Nutzer)"""
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
                s.sold_at
            FROM sales s
            JOIN runs r ON s.run_id = r.id
            WHERE s.item_id = %s OR s.item_id = (SELECT id FROM items WHERE ro_item_id = %s LIMIT 1)
            ORDER BY s.sold_at DESC NULLS LAST, s.id DESC;
        """
        cur.execute(query, (item_id, item_id))
        history = cur.fetchall()
        cur.close()
        conn.close()
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Historie: {str(e)}")


# --- ITEM BEARBEITEN (PUT) - Nur für Admins ---
@router.put("/{id}")
def update_item(
    id: int,
    item: ItemUpdate,
    admin_user: dict = Depends(get_current_admin_user)
):
    """Aktualisiert die Stammdaten eines Items anhand der internen Daten-ID (Nur Admins)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    img_url = item.image_url
    if not img_url and item.item_id:
        img_url = f"/items/{item.item_id}.png"

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

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