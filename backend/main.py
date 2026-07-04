from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import uuid

from backend.graph.workflow import mission_graph
from backend.database.core import engine, Base, SessionLocal
from backend.database.seed import seed_data

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_data(db)
    db.close()
    yield

app = FastAPI(
    title="sUAS Mission Planning API",
    description="Backend orchestration with conditional edges and memory.",
    version="0.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MissionRequest(BaseModel):
    aircraft_id: str
    payload_id: str
    mission_params: Dict[str, Any]
    thread_id: Optional[str] = None  # ADDED: Thread tracking for MemorySaver

@app.get("/health")
def health_check():
    return {"status": "operational", "service": "suas-engine"}

@app.post("/api/plan")
async def plan_mission(request: MissionRequest):
    # Generate a thread ID if not provided
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # ADDED: Pass config to graph for checkpointing
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "aircraft_id": request.aircraft_id,
        "payload_id": request.payload_id,
        "mission_params": request.mission_params,
        "is_viable": True 
    }
    
    final_state = mission_graph.invoke(initial_state, config=config)
    
    return {
        "is_viable": final_state.get("is_viable"),
        "calculations": final_state.get("calculations", {}),
        "weather": final_state.get("weather", {}),
        "report": final_state.get("report", ""),
        "thread_id": thread_id
    }
