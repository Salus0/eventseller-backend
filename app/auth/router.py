import os
import httpx
import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
ADMIN_ROLE_ID = os.getenv("DISCORD_ADMIN_ROLE_ID")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-this")
JWT_ALGORITHM = "HS256"

# Weiterleitung zum Discord Login
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

# Callback nach dem Discord Login
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

        role = "guest"
        if guild_res.status_code == 200:
            member_data = guild_res.json()
            user_roles = member_data.get("roles", [])
            if ADMIN_ROLE_ID in user_roles:
                role = "admin"
            else:
                role = "member"

        # JWT Token erstellen
        payload = {
            "sub": user["id"],
            "username": user["username"],
            "avatar": user.get("avatar"),
            "role": role,
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        frontend_url = os.getenv("FRONTEND_URL", "https://yggdrasil-eventseller.up.railway.app")
        return RedirectResponse(f"{frontend_url}/auth/callback?token={jwt_token}")