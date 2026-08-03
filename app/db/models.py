from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Example(Base):
    __tablename__ = "example"
    id = Column(Integer, primary_key=True)
    name = Column(String)
