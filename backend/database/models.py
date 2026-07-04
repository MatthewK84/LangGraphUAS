from sqlalchemy import Column, String, Float
from backend.database.core import Base

class AircraftDB(Base):
    __tablename__ = "aircraft"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=False)
    max_payload_kg = Column(Float, nullable=False)
    battery_wh = Column(Float, nullable=False)
    max_wind_mps = Column(Float, nullable=False)
    cruise_speed_mps = Column(Float, nullable=False)
    hover_power_w = Column(Float, nullable=False)
    cruise_power_w = Column(Float, nullable=False)
    max_temp_c = Column(Float, nullable=False)

class PayloadDB(Base):
    __tablename__ = "payloads"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=False)
    power_draw_w = Column(Float, nullable=False)
