import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SCHEMAS ---
class RunCreate(BaseModel):
    name: str

class RunStatusUpdate(BaseModel):
    status: str  # z. B. 'open', 'closed', 'completed'

class SaleCreate(BaseModel):
    item_id: int
    quantity: int = 1
    actual_price: int
    is_shop: bool = False
    buyer_name: Optional[str] = None

class RunParticipantAdd(BaseModel):
    participant_id: int

class PayoutStatusUpdate(BaseModel):
    is_paid: bool

# Neue Schemas für Batch-Updates aus dem Frontend
class ParticipantUpdate(BaseModel):
    participant_id: int
    class_name: Optional[str] = "Unbekannt"

class ItemUpdate(BaseModel):
    name: str
    quantity: int = 1


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

# --- RUN LÖSCHEN (DELETE) ---
@router.delete("/{run_id}")
def delete_run(run_id: int):
    """Löscht einen Run inklusive aller zugehörigen Verkäufe und Teilnehmer-Verknüpfungen"""
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

# --- BATCH TEILNEHMER EDITIEREN/SPEICHERN (PUT) ---
@router.put("/{run_id}/participants")
def update_run_participants(run_id: int, participants: List[ParticipantUpdate]):
    """Ersetzt die komplette Teilnehmerliste eines Runs"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # 1. Alte Zuordnungen löschen
        cur.execute("DELETE FROM run_participants WHERE run_id = %s;", (run_id,))
        
        # 2. Neue Liste einfügen
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

# --- BATCH ITEMS/DROPS EDITIEREN/SPEICHERN (PUT) ---
@router.put("/{run_id}/items")
def update_run_items(run_id: int, items: List[ItemUpdate]):
    """Ersetzt alle Drops/Items eines Runs"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # 1. Alte Drops löschen
        cur.execute("DELETE FROM run_drops WHERE run_id = %s;", (run_id,))
        
        # 2. Neue Items/Drops eintragen
        for item in items:
            # Item-ID ermitteln oder neu anlegen, falls noch nicht existent
            cur.execute(
                """
                INSERT INTO items (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name
                RETURNING id;
                """,
                (item.name,)
            )
            item_id = cur.fetchone()['id']

            # Zu Drop-Tabelle hinzufügen
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

# --- ITEMS/DROPS EINES RUNS ABFRAGEN (GET) ---
@router.get("/{run_id}/items")
def get_run_items(run_id: int):
    """Lädt alle Drops/Items eines bestimmten Runs aus der Datenbank"""
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

# --- VERKAUF ZU RUN HINZUFÜGEN (POST) ---
@router.post("/{run_id}/sales")
def add_sale_to_run(run_id: int, sale: SaleCreate):
    """Fügt einem Run einen Item-Verkauf hinzu (inkl. 2% Shop-Abzug-Berechnung)"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")

    # Berechne den finalen Preis mit 2% Abzug, falls über Shop verkauft
    final_price = int(round(sale.actual_price * 0.98)) if sale.is_shop else sale.actual_price

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # Item-Prüfung über ro_item_id
        cur.execute("SELECT id FROM items WHERE ro_item_id = %s OR id = %s LIMIT 1;", (sale.item_id, sale.item_id))
        item_row = cur.fetchone()
        
        if not item_row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Item existiert nicht in der Datenbank!")

        # Eintrag in sales-Tabelle speichern
        cur.execute(
            """
            INSERT INTO sales (run_id, item_id, quantity, actual_price, is_shop, buyer_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (run_id, sale.item_id, sale.quantity, final_price, sale.is_shop, sale.buyer_name)
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

# --- EINZELNEN VERKAUF LÖSCHEN (DELETE) ---
@router.delete("/sales/{sale_id}")
def delete_sale(sale_id: int):
    """Entfernt einen einzelnen Verkaufs-Eintrag"""
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

# --- TEILNEHMER ZUM RUN HINZUFÜGEN (POST) ---
@router.post("/{run_id}/participants")
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

# --- TEILNEHMER EINES RUNS ABFRAGEN (GET) ---
@router.get("/{run_id}/participants")
def get_run_participants(run_id: int):
    """Lädt alle Spieler inklusive aller Details aus der Datenbank"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # LEFT JOIN verhindert, dass die Liste leer bleibt, falls der Name in 'participants' fehlt
        cur.execute(
            """
            SELECT 
                rp.participant_id, 
                COALESCE(p.name, 'Teilnehmer #' || rp.participant_id) as name, 
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

# --- AUSZAHLUNGS-STATUS EINES SPIELERS ÄNDERN (PUT) ---
@router.put("/{run_id}/participants/{participant_id}/payout")
def update_payout_status(run_id: int, participant_id: int, status: PayoutStatusUpdate):
    """Markiert, ob ein Spieler für diesen Run bereits ausgezahlt wurde"""
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

# --- ZENY-SPLIT & ZUSAMMENFASSUNG BERECHNEN (GET) ---
@router.get("/{run_id}/summary")
def get_run_summary(run_id: int):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht gesetzt!")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # 1. Gesamteinnahmen
        cur.execute("SELECT COALESCE(SUM(quantity * actual_price), 0) as total_zeny FROM sales WHERE run_id = %s;", (run_id,))
        total_zeny = cur.fetchone()["total_zeny"]
        
        # 2. Anzahl Teilnehmer
        cur.execute("SELECT COUNT(*) as count FROM run_participants WHERE run_id = %s;", (run_id,))
        participant_count = cur.fetchone()["count"]
        
        # 3. Bereits ausgezahlte Teilnehmer
        cur.execute("SELECT COUNT(*) as paid_count FROM run_participants WHERE run_id = %s AND is_paid = TRUE;", (run_id,))
        paid_count = cur.fetchone()["paid_count"]
        
        # 4. Cut pro Spieler
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