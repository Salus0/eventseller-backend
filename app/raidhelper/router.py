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
            response = await client.get(
                f"https://raid-helper.dev/api/v2/events/{event_id}",
                headers=headers
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail="Raid-Helper Event konnte nicht abgerufen werden."
                )
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Netzwerkfehler: {str(e)}")