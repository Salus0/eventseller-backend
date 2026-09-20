import os
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Depends

# Auth-Dependencies importieren (analog zu deinen anderen Routern)
from app.auth.router import require_member

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def fetch_run_details(run_id: int):
    """
    Hilfsfunktion: Lädt alle relevanten Daten für einen Run aus der Datenbank
    (Run-Infos, Verkäufe/Zeny-Summe und Teilnehmer).
    """
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL ist nicht konfiguriert!")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        # 1. Run-Basisdaten holen
        cur.execute("SELECT * FROM runs WHERE id = %s;", (run_id,))
        run_data = cur.fetchone()

        if not run_data:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Run nicht gefunden")

        # 2. Gesamte Zeny-Einnahmen aus der sales-Tabelle berechnen
        cur.execute(
            "SELECT COALESCE(SUM(quantity * actual_price), 0) as total_zeny FROM sales WHERE run_id = %s;",
            (run_id,)
        )
        total_zeny = cur.fetchone()["total_zeny"]

        # 3. Teilnehmer mit Namen & Discord-ID holen
        cur.execute(
            """
            SELECT 
                rp.participant_id,
                COALESCE(p.name, 'Teilnehmer #' || rp.participant_id) as name,
                p.discord_id,
                COALESCE(rp.class_name, 'Unbekannt') as class_name
            FROM run_participants rp
            LEFT JOIN participants p ON rp.participant_id = p.id
            WHERE rp.run_id = %s;
            """,
            (run_id,)
        )
        participants = cur.fetchall()

        cur.close()
        conn.close()

        # Zeny pro Teilnehmer berechnen
        participant_count = len(participants)
        payout_per_player = int(total_zeny / participant_count) if participant_count > 0 else 0

        return {
            "run": run_data,
            "total_zeny": total_zeny,
            "payout_per_player": payout_per_player,
            "participants": participants
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Run-Daten: {str(e)}")


@router.post("/runs/{run_id}/post", dependencies=[Depends(require_member)])
async def post_run_to_discord(run_id: int):
    """
    Formatiert die Run-Daten und sendet sie als schickes Embed über den Discord Webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        raise HTTPException(
            status_code=500, 
            detail="DISCORD_WEBHOOK_URL ist in den Umgebungsvariablen nicht gesetzt!"
        )

    # 1. Daten laden
    data = fetch_run_details(run_id)
    run = data["run"]
    total_zeny = data["total_zeny"]
    payout_per_player = data["payout_per_player"]
    participants = data["participants"]

    # 2. Teilnehmer-Liste formatieren (inkl. Discord Mention wenn discord_id vorhanden ist)
    if participants:
        participant_lines = []
        for p in participants:
            # Falls discord_id vorhanden ist, benutze <@ID>, damit Discord den User markiert
            user_str = f"<@{p['discord_id']}>" if p.get("discord_id") else f"@{p['name']}"
            class_str = f"({p['class_name']})" if p.get("class_name") and p["class_name"] != "Unbekannt" else ""
            participant_lines.append(f"• {user_str} {class_str}".strip())
        participants_text = "\n".join(participant_lines)
    else:
        participants_text = "*Keine Teilnehmer eingetragen*"

    # Formatiere Zahlen schön (z. B. 1.250.000 Zeny)
    formatted_total = f"{total_zeny:,}".replace(",", ".")
    formatted_payout = f"{payout_per_player:,}".replace(",", ".")

    # Web-App URL zum Run
    frontend_url = os.getenv("FRONTEND_URL", "https://eventseller-frontend.vercel.app/")
    run_link = f"{frontend_url}/runs?open={run_id}"

    # 3. Discord Embed payload aufbauen
    payload = {
        "username": "Yggdrasil Event-Seller",
        "embeds": [
            {
                "color": 5093762,  # Yggdrasil Grün (Hex: #4DB982)
                "description": (
                    "```yaml\n"
                    "Es wurde alles verkauft !\n"  # Goldene/Gelbe Schrift im Codeblock
                    "```\n"
                    f"**Gesamteinnahmen:** {formatted_total} Zeny\n"
                    f"**Split für jeden:** {formatted_payout} Zeny\n\n"
                    f"**Teilnehmer ({len(participants)}):**\n"
                    f"{participants_text}\n\n"
                    f"🔗 **Direkt-Link:** [Zum Run #{run_id}]({run_link})"
                ),
                "footer": {
                    "text": f"Yggdrasil Event-Seller • Link: {run_link}"
                }
            }
        ]
    }

    # 4. Request an Discord senden
    async with httpx.AsyncClient() as client:
        response = await client.post(DISCORD_WEBHOOK_URL, json=payload)
        
        if response.status_code not in (200, 204):
            raise HTTPException(
                status_code=500, 
                detail=f"Discord Webhook Fehler: {response.status_code} - {response.text}"
            )

    return {"message": "Erfolgreich auf Discord gepostet!", "run_id": run_id}