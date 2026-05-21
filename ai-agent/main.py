from fastapi import FastAPI

app = FastAPI(
    title="Workmaite AI Agent",
    description="Workmaite AI Agent Service",
    version="0.0.1",
)


@app.get("/health")
def health():
    return {"status": "UP"}
