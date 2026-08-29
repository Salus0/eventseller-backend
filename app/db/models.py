from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Example(Base):
    __tablename__ = "example"
    id = Column(Integer, primary_key=True)
    name = Column(String)

class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    discord_id = Column(String, nullable=True)