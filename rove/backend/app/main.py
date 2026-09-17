from fastapi import FastAPI

app = FastAPI(title="Rove Agent API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
