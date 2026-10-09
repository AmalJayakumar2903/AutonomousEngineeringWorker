from fastapi import FastAPI

app = FastAPI(
    title="Autonomous Engineering Worker",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "autonomous-engineering-worker",
    }
