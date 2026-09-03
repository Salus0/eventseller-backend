import os

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.auth.router import require_member, require_seller, require_admin
from app.db.database import get_connection, release_connection


router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")


# ============================================================
# SCHEMAS
# ============================================================

class RunCreate(BaseModel):
    name: str
    created_at: Optional[str] = None


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


# ============================================================
# RUN ERSTELLEN
# ============================================================

@router.post("/", dependencies=[Depends(require_seller)])
def create_run(run: RunCreate):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        if run.created_at:
            cur.execute(
                """
                INSERT INTO runs (name, created_at)
                VALUES (%s, %s)
                RETURNING *;
                """,
                (run.name, run.created_at)
            )
        else:
            cur.execute(
                """
                INSERT INTO runs (name)
                VALUES (%s)
                RETURNING *;
                """,
                (run.name,)
            )

        new_run = cur.fetchone()

        conn.commit()

        return new_run

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# ALLE RUNS
# ============================================================

@router.get("/", dependencies=[Depends(require_member)])
def get_runs():

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=None)

        cur.execute(
            """
            SELECT *
            FROM runs
            ORDER BY id DESC;
            """
        )

        runs = cur.fetchall()

        return runs

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# RUN OVERVIEW
#
# Liefert alle für die Run-Liste benötigten Statusinformationen
# in EINER Datenbankabfrage.
# ============================================================

@router.get("/overview", dependencies=[Depends(require_member)])
def get_runs_overview():

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=None)

        query = """
            WITH item_totals AS (
                SELECT
                    rd.run_id,
                    COALESCE(SUM(rd.amount), 0) AS total_items
                FROM run_drops rd
                GROUP BY rd.run_id
            ),

            sold_totals AS (
                SELECT
                    s.run_id,
                    COALESCE(SUM(s.quantity), 0) AS sold_items
                FROM sales s
                GROUP BY s.run_id
            ),

            participant_totals AS (
                SELECT
                    rp.run_id,
                    COUNT(*) AS total_participants,
                    COUNT(*) FILTER (
                        WHERE COALESCE(rp.is_paid, FALSE) = TRUE
                    ) AS paid_participants
                FROM run_participants rp
                GROUP BY rp.run_id
            )

            SELECT
                r.id,
                r.name,
                r.run_type,
                r.created_at,
                r.status AS database_status,

                COALESCE(it.total_items, 0) AS total_items,

                LEAST(
                    COALESCE(st.sold_items, 0),
                    COALESCE(it.total_items, 0)
                ) AS sold_items,

                COALESCE(pt.total_participants, 0)
                    AS total_participants,

                COALESCE(pt.paid_participants, 0)
                    AS paid_participants,

                CASE

                    WHEN COALESCE(it.total_items, 0) > 0
                     AND COALESCE(st.sold_items, 0)
                         >= COALESCE(it.total_items, 0)
                     AND COALESCE(pt.total_participants, 0) > 0
                     AND COALESCE(pt.paid_participants, 0)
                         = COALESCE(pt.total_participants, 0)

                    THEN 'Close'

                    WHEN COALESCE(it.total_items, 0) > 0
                     AND COALESCE(st.sold_items, 0)
                         >= COALESCE(it.total_items, 0)

                    THEN 'Payout'

                    WHEN COALESCE(it.total_items, 0) > 0

                    THEN 'On Sale'

                    ELSE NULL

                END AS calculated_status

            FROM runs r

            LEFT JOIN item_totals it
                ON it.run_id = r.id

            LEFT JOIN sold_totals st
                ON st.run_id = r.id

            LEFT JOIN participant_totals pt
                ON pt.run_id = r.id

            ORDER BY r.created_at DESC NULLS LAST, r.id DESC;
        """

        cur.execute(query)

        overview = cur.fetchall()

        return overview

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Laden der Run-Übersicht: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# RUN BEARBEITEN
# ============================================================

@router.put("/{run_id}", dependencies=[Depends(require_seller)])
def update_run(run_id: int, run: RunUpdate):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
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

        if not updated_run:
            raise HTTPException(
                status_code=404,
                detail="Run nicht gefunden"
            )

        conn.commit()

        return updated_run

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Aktualisieren des Runs: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# RUN LÖSCHEN
# ============================================================

@router.delete("/{run_id}", dependencies=[Depends(require_admin)])
def delete_run(run_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM runs
            WHERE id = %s
            RETURNING *;
            """,
            (run_id,)
        )

        deleted_run = cur.fetchone()

        if not deleted_run:
            raise HTTPException(
                status_code=404,
                detail="Run nicht gefunden"
            )

        conn.commit()

        return {
            "message": f"Run '{deleted_run['name']}' erfolgreich gelöscht"
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Löschen: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# BATCH TEILNEHMER SPEICHERN
# ============================================================

@router.put("/{run_id}/participants", dependencies=[Depends(require_seller)])
def update_run_participants(
    run_id: int,
    participants: List[ParticipantUpdate]
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM run_participants
            WHERE run_id = %s;
            """,
            (run_id,)
        )

        for p in participants:
            cur.execute(
                """
                INSERT INTO run_participants
                    (run_id, participant_id, class_name)
                VALUES
                    (%s, %s, %s);
                """,
                (
                    run_id,
                    p.participant_id,
                    p.class_name
                )
            )

        conn.commit()

        return {
            "message": "Teilnehmer erfolgreich gespeichert"
        }

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Speichern der Teilnehmer: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# BATCH ITEMS SPEICHERN
# ============================================================

@router.put("/{run_id}/items", dependencies=[Depends(require_seller)])
def update_run_items(
    run_id: int,
    items: List[ItemUpdate]
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM run_drops
            WHERE run_id = %s;
            """,
            (run_id,)
        )

        for item in items:

            cur.execute(
                """
                INSERT INTO items (name)
                VALUES (%s)
                ON CONFLICT (name)
                DO UPDATE SET name = EXCLUDED.name
                RETURNING id;
                """,
                (item.name,)
            )

            item_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO run_drops
                    (run_id, item_id, amount)
                VALUES
                    (%s, %s, %s);
                """,
                (
                    run_id,
                    item_id,
                    item.quantity
                )
            )

        conn.commit()

        return {
            "message": "Items erfolgreich gespeichert"
        }

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Speichern der Items: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# ITEMS/DROPS ABFRAGEN
# ============================================================

@router.get("/{run_id}/items", dependencies=[Depends(require_member)])
def get_run_items(run_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                rd.item_id,
                rd.amount AS quantity,
                i.name AS item_name
            FROM run_drops rd
            LEFT JOIN items i
                ON rd.item_id = i.id
            WHERE rd.run_id = %s;
            """,
            (run_id,)
        )

        items = cur.fetchall()

        return items

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Laden der Items: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# VERKAUF HINZUFÜGEN
# ============================================================

@router.post("/{run_id}/sales", dependencies=[Depends(require_seller)])
def add_sale_to_run(
    run_id: int,
    sale: SaleCreate
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    final_price = (
        int(round(sale.actual_price * 0.98))
        if sale.is_shop
        else sale.actual_price
    )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM items
            WHERE ro_item_id = %s
               OR id = %s
            LIMIT 1;
            """,
            (
                sale.item_id,
                sale.item_id
            )
        )

        item_row = cur.fetchone()

        if not item_row:

            cur.execute(
                """
                INSERT INTO items
                    (name, ro_item_id)
                VALUES
                    (%s, %s)
                RETURNING id;
                """,
                (
                    f"Item #{sale.item_id}",
                    sale.item_id
                )
            )

            item_db_id = cur.fetchone()["id"]

        else:
            item_db_id = item_row["id"]

        cur.execute(
            """
            INSERT INTO sales
                (
                    run_id,
                    item_id,
                    quantity,
                    actual_price,
                    is_shop
                )
            VALUES
                (%s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (
                run_id,
                item_db_id,
                sale.quantity,
                final_price,
                sale.is_shop
            )
        )

        new_sale = cur.fetchone()

        conn.commit()

        return new_sale

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Speichern des Verkaufs: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# VERKÄUFE ABFRAGEN
# ============================================================

@router.get("/{run_id}/sales", dependencies=[Depends(require_member)])
def get_run_sales(run_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                s.*,
                i.name AS item_name,
                i.ro_item_id
            FROM sales s
            LEFT JOIN items i
                ON s.item_id = i.id
            WHERE s.run_id = %s
            ORDER BY s.id ASC;
            """,
            (run_id,)
        )

        sales = cur.fetchall()

        return sales

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# VERKAUF BEARBEITEN
# ============================================================

@router.put("/sales/{sale_id}", dependencies=[Depends(require_seller)])
def update_sale(
    sale_id: int,
    sale: SaleUpdate
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    final_price = (
        int(round(sale.actual_price * 0.98))
        if sale.is_shop
        else sale.actual_price
    )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM sales
            WHERE id = %s;
            """,
            (sale_id,)
        )

        existing = cur.fetchone()

        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Verkaufseintrag nicht gefunden"
            )

        cur.execute(
            """
            UPDATE sales
            SET
                quantity = %s,
                actual_price = %s,
                is_shop = %s
            WHERE id = %s
            RETURNING *;
            """,
            (
                sale.quantity,
                final_price,
                sale.is_shop,
                sale_id
            )
        )

        updated_sale = cur.fetchone()

        conn.commit()

        return updated_sale

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Aktualisieren des Verkaufs: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# VERKAUF LÖSCHEN
# ============================================================

@router.delete("/sales/{sale_id}", dependencies=[Depends(require_seller)])
def delete_sale(sale_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM sales
            WHERE id = %s
            RETURNING *;
            """,
            (sale_id,)
        )

        deleted_sale = cur.fetchone()

        if not deleted_sale:
            raise HTTPException(
                status_code=404,
                detail="Verkauf nicht gefunden"
            )

        conn.commit()

        return {
            "message": "Verkauf erfolgreich entfernt"
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Löschen: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# TEILNEHMER HINZUFÜGEN
# ============================================================

@router.post("/{run_id}/participants", dependencies=[Depends(require_seller)])
def add_participant_to_run(
    run_id: int,
    entry: RunParticipantAdd
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO run_participants
                (run_id, participant_id)
            VALUES
                (%s, %s)
            RETURNING *;
            """,
            (
                run_id,
                entry.participant_id
            )
        )

        result = cur.fetchone()

        conn.commit()

        return result

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Hinzufügen: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# TEILNEHMER ABFRAGEN
# ============================================================

@router.get("/{run_id}/participants", dependencies=[Depends(require_member)])
def get_run_participants(run_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                rp.participant_id,

                COALESCE(
                    p.name,
                    'Teilnehmer #' || rp.participant_id
                ) AS name,

                p.discord_id,

                COALESCE(
                    rp.class_name,
                    'Unbekannt'
                ) AS class_name,

                COALESCE(
                    rp.is_paid,
                    FALSE
                ) AS is_paid

            FROM run_participants rp

            LEFT JOIN participants p
                ON rp.participant_id = p.id

            WHERE rp.run_id = %s;
            """,
            (run_id,)
        )

        participants = cur.fetchall()

        return participants

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Laden der Teilnehmer: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# AUSZAHLUNGSSTATUS ÄNDERN
# ============================================================

@router.put(
    "/{run_id}/participants/{participant_id}/payout",
    dependencies=[Depends(require_seller)]
)
def update_payout_status(
    run_id: int,
    participant_id: int,
    status: PayoutStatusUpdate
):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE run_participants
            SET is_paid = %s
            WHERE run_id = %s
              AND participant_id = %s
            RETURNING *;
            """,
            (
                status.is_paid,
                run_id,
                participant_id
            )
        )

        updated_entry = cur.fetchone()

        if not updated_entry:
            raise HTTPException(
                status_code=404,
                detail="Eintrag nicht gefunden"
            )

        conn.commit()

        return updated_entry

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Aktualisieren des Payouts: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)


# ============================================================
# ZENY-SUMMARY
# ============================================================

@router.get("/{run_id}/summary", dependencies=[Depends(require_member)])
def get_run_summary(run_id: int):

    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL ist nicht gesetzt!"
        )

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Gesamt-Zeny
        cur.execute(
            """
            SELECT
                COALESCE(
                    SUM(quantity * actual_price),
                    0
                ) AS total_zeny

            FROM sales

            WHERE run_id = %s;
            """,
            (run_id,)
        )

        total_zeny = cur.fetchone()["total_zeny"]

        # Teilnehmer
        cur.execute(
            """
            SELECT
                COUNT(*) AS count

            FROM run_participants

            WHERE run_id = %s;
            """,
            (run_id,)
        )

        participant_count = cur.fetchone()["count"]

        # Ausgezahlte Teilnehmer
        cur.execute(
            """
            SELECT
                COUNT(*) AS paid_count

            FROM run_participants

            WHERE run_id = %s
              AND is_paid = TRUE;
            """,
            (run_id,)
        )

        paid_count = cur.fetchone()["paid_count"]

        payout_per_player = (
            int(total_zeny / participant_count)
            if participant_count > 0
            else 0
        )

        return {
            "run_id": run_id,
            "total_zeny": total_zeny,
            "participant_count": participant_count,
            "payout_per_player": payout_per_player,
            "participants_paid": paid_count,
            "all_paid_out": (
                participant_count > 0
                and participant_count == paid_count
            )
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Berechnung: {str(e)}"
        )

    finally:
        if cur:
            cur.close()

        release_connection(conn)