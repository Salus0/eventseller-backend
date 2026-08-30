import os
import httpx
import jwt
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# --- DISCORD ROLLEN EINSTELLUNGEN ---
# Du kannst hier Komma-getrennte IDs in der Railway Env-Variable speichern 
# oder die IDs direkt als Liste definieren:
ADMIN_ROLE_IDS = os.getenv("DISCORD_ADMIN_ROLE_IDS", "1520133746462822480").split(",")
SELLER_ROLE_IDS = os.getenv("DISCORD_SELLER_ROLE_IDS", "1520149616065122384").split(",")
MEMBER_ROLE_IDS = os.getenv("DISCORD_MEMBER_ROLE_IDS", "1520141680185970688,1528056559307853916,1529563768244404314,1520144730669711440").split(",")

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-this")
JWT_ALGORITHM = "HS256"

security = HTTPBearer()

# --- HELFER ZUM PRÜFEN DER ROLLEN IN API-ENDPUNKTEN ---

def get_current_user_payload(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Ungültiger Token. Bitte erneut einloggen."
        )

def get_current_user_role(payload: dict = Depends(get_current_user_payload)) -> str:
    user_roles = [str(r) for r in payload.get("roles", [])]
    
    # 1. Admin Check
    if any(r in user_roles for r in ADMIN_ROLE_IDS) or payload.get("role") == "admin":
        return "admin"
        
    # 2. Seller Check
    if any(r in user_roles for r in SELLER_ROLE_IDS) or payload.get("role") == "seller":
        return "seller"
        
    # 3. Member Check (mehrere Rollen erlaubt)
    if any(r in user_roles for r in MEMBER_ROLE_IDS) or payload.get("role") == "member":
        return "member"
        
    # Falls der User auf dem Discord ist, aber keine der 3 Rollen hat:
    raise HTTPException(
        status_code=403, 
        detail="Zugriff verweigert: Keine berechtigte Discord-Rolle vorhanden."
    )

# --- DEPENDENCIES FÜR ROUTEN-SCHUTZ ---

def require_member(role: str = Depends(get_current_user_role)):
    if role not in ["admin", "seller", "member"]:
        raise HTTPException(status_code=403, detail="Keine Leseberechtigung")
    return role

def require_seller(role: str = Depends(get_current_user_role)):
    if role not in ["admin", "seller"]:
        raise HTTPException(status_code=403, detail="Mindestens Seller-Rolle erforderlich")
    return role

def require_admin(role: str = Depends(get_current_user_role)):
    if role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins gestattet")
    return role


# --- AUTH ENDPUNKTE ---

@router.get("/login")
def discord_login():
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds.members.read"
    )
    return RedirectResponse(discord_auth_url)

@router.get("/discord/callback")
async def discord_callback(code: str):
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://discord.com/api/oauth2/token", data=token_data, headers=headers)
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Discord Token Fehler")
        
        tokens = token_res.json()
        access_token = tokens.get("access_token")

        # Discord Profildaten holen
        user_res = await client.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        user = user_res.json()

        # Gildenmitgliedschaft & Rollen prüfen
        guild_res = await client.get(
            f"https://discord.com/api/users/@me/guilds/{GUILD_ID}/member", 
            headers={"Authorization": f"Bearer {access_token}"}
        )

        role = "unauthorized"
        user_roles = []

        if guild_res.status_code == 200:
            member_data = guild_res.json()
            user_roles = [str(r) for r in member_data.get("roles", [])]

            # Hierarchie prüfen
            if any(r in user_roles for r in ADMIN_ROLE_IDS):
                role = "admin"
            elif any(r in user_roles for r in SELLER_ROLE_IDS):
                role = "seller"
            elif any(r in user_roles for r in MEMBER_ROLE_IDS):
                role = "member"

        # JWT Token mit allen Discord-Rollen-IDs erstellen
        payload = {
            "sub": user["id"],
            "discord_id": user["id"],
            "username": user["username"],
            "avatar": user.get("avatar"),
            "role": role,
            "roles": user_roles,
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        frontend_url = os.getenv("FRONTEND_URL", "https://yggdrasil-eventseller.up.railway.app")
        return RedirectResponse(f"{frontend_url}/auth/callback?token={jwt_token}")