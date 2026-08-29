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
        # Falls der Key in Railway ohne Bearer/Key Schema vorliegt:
        headers["Authorization"] = RAID_HELPER_API_KEY

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://raid-helper.dev/api/v2/events/{event_id}",
                headers=headers,
                timeout=10.0
            )
            
            # Falls Raid-Helper z.B. 401 Unauthorized oder 404 zurückgibt:
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Raid-Helper API meldet Status {response.status_code}: {response.text}"
                )
                
            return response.json()
            
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502, 
                detail=f"Verbindungsfehler zu Raid-Helper: {str(exc)}"
            )