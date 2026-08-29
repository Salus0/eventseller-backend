import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

RAID_HELPER_API_KEY = os.getenv("RAID_HELPER_API_KEY")

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
            # Aktualisiert auf API v4
            url = f"https://raid-helper.xyz/api/v4/events/{event_id}"
            response = await client.get(url, headers=headers, timeout=10.0)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Raid-Helper v4 Fehler ({response.status_code}): {response.text}"
                )
                
            return response.json()
            
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502, 
                detail=f"Verbindungsfehler zu Raid-Helper: {str(exc)}"
            )