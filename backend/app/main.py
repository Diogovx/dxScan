from fastapi import FastAPI
from app.core.database import engine
from app.models import scanner_data
from app.routes import inventory

scanner_data.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="DXSCAN API", 
    description="API for hardware and software inventory collection",
    version="1.0.0"
)

app.include_router(inventory.router)

@app.get("/")
def read_root():
    return {"message": "DXSCAN API is online and ready to receive data!"}