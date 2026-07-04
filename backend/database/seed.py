import json
from sqlalchemy.orm import Session
from backend.database.models import AircraftDB, PayloadDB

def seed_data(db: Session):
    if db.query(AircraftDB).first(): return
    with open("data/aircraft.json", "r") as f:
        for _, val in json.load(f).items(): db.add(AircraftDB(**val))
    with open("data/payloads.json", "r") as f:
        for _, val in json.load(f).items(): db.add(PayloadDB(**val))
    db.commit()
