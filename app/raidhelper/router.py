import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

RAID_HELPER_API_KEY = os.getenv("RAID_HELPER_API_KEY")
DISCORD_SERVER_ID = "1520129742739607563"

@router.get("/test")
def test():
    return {"raidhelper": "ok"}

@router.get("/event/{event_id}")
async def get_raid_helper_event(event_id: str):
    headers = {}
    if RAID_HELPER_API_KEY:
        headers["Authorization"] = RAID_HELPER_API_KEY

    async with httpx.AsyncClient() as client:
        try:
            # Korrigierter API-Pfad mit Server-ID und Event-ID
            url = f"https://raid-helper.dev/api/v2/servers/{DISCORD_SERVER_ID}/events/{event_id}"
            response = await client.get(url, headers=headers, timeout=10.0)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Raid-Helper Fehler ({response.status_code}): {response.text}"
                )
                
            return response.json()
            
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502, 
                detail=f"Verbindungsfehler zu Raid-Helper: {str(exc)}"
            )