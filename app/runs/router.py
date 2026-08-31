import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

# Auth Dependencies aus der auth.py importieren
from app.auth.router import require_member, require_seller, require_admin

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMAS ---
class RunCreate(BaseModel):
    name: str
    created_at: Optional[str] = None  # z.B. "2026-07-24 20:15:00"

class RunUpdate(BaseModel):
    name: str

class RunStatusUpdate(BaseModel):
    status: str

class SaleCreate(BaseModel):
    item_id: int
    quantity: int = 1
    actual_price: int
    is_shop: bool = False

class RunParticipantAdd(BaseModel):
    participant_id: int

class PayoutStatusUpdate(BaseModel):
    is_paid: bool

class ParticipantUpdate(BaseModel):
    participant_id: int
    class_name: Optional[str] = "Unbekannt"

class ItemUpdate(BaseModel):
    name: str
    quantity: int = 1

class SaleUpdate(BaseModel):
    quantity: int = 1
    actual_price: int
    is_shop: bool = False

# --- RUN ERSTELLEN (POST) - Mindestens SELLER ---
@router.post("/", dependencies=[Depends(require_seller)])
def create_run(run: RunCreate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        if run.created_at:
            cur.execute(
                "INSERT INTO runs (name, created_at) VALUES (%s, %s) RETURNING *;",
                (run.name, run.created_at)
            )
        else:
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
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

# --- ALLE RUNS ABFRAGEN (GET) - Mindestens MEMBER ---
@router.get("/", dependencies=[Depends(require_member)])
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

# --- RUN BEARBEITEN (PUT) - Mindestens SELLER ---
@router.put("/{run_id}", dependencies=[Depends(require_seller)])
def update_run(run_id: int, run: RunUpdate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE runs 
            SET name = %s 
            WHERE id = %s 
            RETURNING *;
            """,
            (run.name, run_id)
        )
        updated_run = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not updated_run:
            raise HTTPException(status_code=404, detail="Run nicht gefunden")
        return updated_run
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren des Runs: {str(e)}")

# --- RUN LÖSCHEN (DELETE) - Nur ADMIN ---
@router.delete("/{run_id}", dependencies=[Depends(require_admin)])
def delete_run(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("DELETE FROM runs WHERE id = %s RETURNING *;", (run_id,))
        deleted_run = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not deleted_run:
            raise HTTPException(status_code=404, detail="Run nicht gefunden")
        return {"message": f"Run '{deleted_run['name']}' erfolgreich gelöscht"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")

# --- BATCH TEILNEHMER SPEICHERN (PUT) - Mindestens SELLER ---
@router.put("/{run_id}/participants", dependencies=[Depends(require_seller)])
def update_run_participants(run_id: int, participants: List[ParticipantUpdate]):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("DELETE FROM run_participants WHERE run_id = %s;", (run_id,))
        for p in participants:
            cur.execute(
                """
                INSERT INTO run_participants (run_id, participant_id, class_name)
                VALUES (%s, %s, %s);
                """,
                (run_id, p.participant_id, p.class_name)
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Teilnehmer erfolgreich gespeichert"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern der Teilnehmer: {str(e)}")

# --- BATCH ITEMS SPEICHERN (PUT) - Mindestens SELLER ---
@router.put("/{run_id}/items", dependencies=[Depends(require_seller)])
def update_run_items(run_id: int, items: List[ItemUpdate]):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("DELETE FROM run_drops WHERE run_id = %s;", (run_id,))
        for item in items:
            cur.execute(
                """
                INSERT INTO items (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name
                RETURNING id;
                """,
                (item.name,)
            )
            item_id = cur.fetchone()['id']
            cur.execute(
                """
                INSERT INTO run_drops (run_id, item_id, amount)
                VALUES (%s, %s, %s);
                """,
                (run_id, item_id, item.quantity)
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Items erfolgreich gespeichert"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern der Items: {str(e)}")

# --- ITEMS/DROPS ABFRAGEN (GET) - Mindestens MEMBER ---
@router.get("/{run_id}/items", dependencies=[Depends(require_member)])
def get_run_items(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                rd.item_id,
                rd.amount as quantity,
                i.name as item_name
            FROM run_drops rd
            LEFT JOIN items i ON rd.item_id = i.id
            WHERE rd.run_id = %s;
            """,
            (run_id,)
        )
        items = cur.fetchall()
        cur.close()
        conn.close()
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Items: {str(e)}")

# --- VERKAUF HINZUFÜGEN (POST) - Mindestens SELLER ---
@router.post("/{run_id}/sales", dependencies=[Depends(require_seller)])
def add_sale_to_run(run_id: int, sale: SaleCreate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    final_price = int(round(sale.actual_price * 0.98)) if sale.is_shop else sale.actual_price

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("SELECT id FROM items WHERE ro_item_id = %s OR id = %s LIMIT 1;", (sale.item_id, sale.item_id))
        item_row = cur.fetchone()
        
        if not item_row:
            cur.execute(
                "INSERT INTO items (name, ro_item_id) VALUES (%s, %s) RETURNING id;",
                (f"Item #{sale.item_id}", sale.item_id)
            )
            item_db_id = cur.fetchone()['id']
        else:
            item_db_id = item_row['id']

        cur.execute(
            """
            INSERT INTO sales (run_id, item_id, quantity, actual_price, is_shop)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (run_id, item_db_id, sale.quantity, final_price, sale.is_shop)
        )
        new_sale = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return new_sale
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern des Verkaufs: {str(e)}")

# --- VERKÄUFE ABFRAGEN (GET) - Mindestens MEMBER ---
@router.get("/{run_id}/sales", dependencies=[Depends(require_member)])
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

# --- VERKAUF BEARBEITEN (PUT) - Mindestens SELLER ---
@router.put("/sales/{sale_id}", dependencies=[Depends(require_seller)])
def update_sale(sale_id: int, sale: SaleUpdate):
    """Aktualisiert Preis, Menge oder Shop-Status eines bestehenden Verkaufs"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    final_price = int(round(sale.actual_price * 0.98)) if sale.is_shop else sale.actual_price

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("SELECT id FROM sales WHERE id = %s;", (sale_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Verkaufseintrag nicht gefunden")

        cur.execute(
            """
            UPDATE sales 
            SET quantity = %s, actual_price = %s, is_shop = %s 
            WHERE id = %s 
            RETURNING *;
            """,
            (sale.quantity, final_price, sale.is_shop, sale_id)
        )
        updated_sale = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return updated_sale
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren des Verkaufs: {str(e)}")

# --- VERKAUF LÖSCHEN (DELETE) - Mindestens SELLER ---
@router.delete("/sales/{sale_id}", dependencies=[Depends(require_seller)])
def delete_sale(sale_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("DELETE FROM sales WHERE id = %s RETURNING *;", (sale_id,))
        deleted_sale = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not deleted_sale:
            raise HTTPException(status_code=404, detail="Verkauf nicht gefunden")
        return {"message": "Verkauf erfolgreich entfernt"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")

# --- TEILNEHMER HINZUFÜGEN (POST) - Mindestens SELLER ---
@router.post("/{run_id}/participants", dependencies=[Depends(require_seller)])
def add_participant_to_run(run_id: int, entry: RunParticipantAdd):
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
        raise HTTPException(status_code=500, detail=f"Fehler beim Hinzufügen: {str(e)}")

# --- TEILNEHMER ABFRAGEN (GET) - Mindestens MEMBER ---
@router.get("/{run_id}/participants", dependencies=[Depends(require_member)])
def get_run_participants(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                rp.participant_id, 
                COALESCE(p.name, 'Teilnehmer #' || rp.participant_id) as name, 
                p.discord_id,
                COALESCE(rp.class_name, 'Unbekannt') as class_name,
                COALESCE(rp.is_paid, FALSE) as is_paid
            FROM run_participants rp
            LEFT JOIN participants p ON rp.participant_id = p.id
            WHERE rp.run_id = %s;
            """,
            (run_id,)
        )
        participants = cur.fetchall()
        cur.close()
        conn.close()
        return participants
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Teilnehmer: {str(e)}")

# --- AUSZAHLUNGS-STATUS ÄNDERN (PUT) - Nur ADMIN ---
@router.put("/{run_id}/participants/{participant_id}/payout", dependencies=[Depends(require_admin)])
def update_payout_status(run_id: int, participant_id: int, status: PayoutStatusUpdate):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE run_participants
            SET is_paid = %s
            WHERE run_id = %s AND participant_id = %s
            RETURNING *;
            """,
            (status.is_paid, run_id, participant_id)
        )
        updated_entry = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not updated_entry:
            raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
        return updated_entry
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Aktualisieren des Payouts: {str(e)}")

# --- ZENY-SPLIT BERECHNEN (GET) - Mindestens MEMBER ---
@router.get("/{run_id}/summary", dependencies=[Depends(require_member)])
def get_run_summary(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        cur.execute("SELECT COALESCE(SUM(quantity * actual_price), 0) as total_zeny FROM sales WHERE run_id = %s;", (run_id,))
        total_zeny = cur.fetchone()["total_zeny"]
        
        cur.execute("SELECT COUNT(*) as count FROM run_participants WHERE run_id = %s;", (run_id,))
        participant_count = cur.fetchone()["count"]
        
        cur.execute("SELECT COUNT(*) as paid_count FROM run_participants WHERE run_id = %s AND is_paid = TRUE;", (run_id,))
        paid_count = cur.fetchone()["paid_count"]
        
        payout_per_player = int(total_zeny / participant_count) if participant_count > 0 else 0
        
        cur.close()
        conn.close()
        
        return {
            "run_id": run_id,
            "total_zeny": total_zeny,
            "participant_count": participant_count,
            "payout_per_player": payout_per_player,
            "participants_paid": paid_count,
            "all_paid_out": participant_count > 0 and participant_count == paid_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei der Berechnung: {str(e)}")