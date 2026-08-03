from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.runs.router import router as runs_router
from app.items.router import router as items_router
from app.participants.router import router as participants_router
from app.discord.router import router as discord_router
from app.raidhelper.router import router as raidhelper_router

app = FastAPI(title="Eventseller Backend")

app.include_router(auth_router, prefix="/auth")
app.include_router(runs_router, prefix="/runs")
app.include_router(items_router, prefix="/items")
app.include_router(participants_router, prefix="/participants")
app.include_router(discord_router, prefix="/discord")
app.include_router(raidhelper_router, prefix="/raidhelper")
