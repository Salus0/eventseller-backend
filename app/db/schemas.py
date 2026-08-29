from pydantic import BaseModel
from typing import Optional

# Basis-Schema mit den gemeinsamen Feldern
class ParticipantBase(BaseModel):
    name: str
    discord_id: Optional[str] = None

# Schema für das Erstellen (POST)
class ParticipantCreate(ParticipantBase):
    pass

# Schema für das Bearbeiten (PUT)
class ParticipantUpdate(ParticipantBase):
    pass

# Schema für die Antwort an das Frontend (GET)
class ParticipantResponse(ParticipantBase):
    id: int

    class Config:
        from_attributes = True  # Erlaubt Pydantic das Auslesen von SQLAlchemy-Modellen