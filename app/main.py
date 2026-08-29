import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

from app.auth.router import router as auth_router
from app.runs.router import router as runs_router
from app.items.router import router as items_router
from app.participants.router import router as participants_router
from app.discord.router import router as discord_router
from app.raidhelper.router import router as raidhelper_router

app = FastAPI(title="Eventseller Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

# --- MAGISCHER TEST-ENDPUNKT ---
@app.get("/init-db")
def force_init_db():
    """Erstellt die Tabellen manuell über den Aufruf im Browser"""
    if not DATABASE_URL:
        return {"status": "Fehler", "details": "DATABASE_URL Umgebungsvariable fehlt!"}
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            discord_id VARCHAR(50)
        );

        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            default_price BIGINT DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS runs (
            id SERIAL PRIMARY KEY,
            run_type VARCHAR(20) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'Offen'
        );

        CREATE TABLE IF NOT EXISTS run_participants (
            run_id INT REFERENCES runs(id) ON DELETE CASCADE,
            participant_id INT REFERENCES participants(id) ON DELETE CASCADE,
            class_name VARCHAR(50) DEFAULT 'Unbekannt',
            payout_status BOOLEAN DEFAULT FALSE,
            payout_amount BIGINT DEFAULT 0,
            PRIMARY KEY (run_id, participant_id)
        );

        CREATE TABLE IF NOT EXISTS run_drops (
            id SERIAL PRIMARY KEY,
            run_id INT REFERENCES runs(id) ON DELETE CASCADE,
            item_id INT REFERENCES items(id) ON DELETE CASCADE,
            amount INT DEFAULT 1,
            sale_type VARCHAR(20) DEFAULT 'Direkt',
            sale_price BIGINT DEFAULT 0,
            net_revenue BIGINT DEFAULT 0,
            is_sold BOOLEAN DEFAULT FALSE
        );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "Erfolg", "message": "Alle Tabellen wurden erfolgreich in PostgreSQL angelegt!"}
    except Exception as e:
        return {"status": "Fehler", "details": str(e)}


# Standard-Router einbinden
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(runs_router, prefix="/runs")
app.include_router(items_router, prefix="/items", tags=["Items"])
app.include_router(participants_router, prefix="/participants")
app.include_router(discord_router, prefix="/discord")
app.include_router(raidhelper_router, prefix="/raidhelper")
