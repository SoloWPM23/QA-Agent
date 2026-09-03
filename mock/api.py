"""Mock REST API for end-to-end QA agent testing.

Run with:

    venv/Scripts/python.exe -m uvicorn mock.api:app --host 127.0.0.1 --port 9000 --reload

The API exposes 10 endpoints. Two of them contain deliberate bugs so the
verifier can demonstrate FAIL verdicts:

- Bug A: GET /api/v1/users/1 returns ``id`` as a string instead of a number.
- Bug B: GET /api/v1/books/99 returns HTTP 200 with an error body instead of 404.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

app = FastAPI(title="Mock API for QA Agent E2E Test")

_INITIAL_USERS = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
}

_INITIAL_BOOKS = {
    1: {"id": 1, "title": "Python 101", "author": "John Doe"},
    2: {"id": 2, "title": "FastAPI Basics", "author": "Jane Smith"},
}

USERS = dict(_INITIAL_USERS)
BOOKS = dict(_INITIAL_BOOKS)


class CreateUserPayload(BaseModel):
    name: str
    email: str


class UpdateUserPayload(BaseModel):
    name: str | None = None
    email: str | None = None


class LoginPayload(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/reset")
def reset_state():
    """Reset mock data to its initial state for repeatable testing."""
    global USERS, BOOKS
    USERS = dict(_INITIAL_USERS)
    BOOKS = dict(_INITIAL_BOOKS)
    return {"status": "ok"}


@app.get("/api/v1/users")
def list_users():
    return {"users": list(USERS.values())}


@app.get("/api/v1/users/{user_id}")
def get_user(user_id: int):
    # Bug A: user 1 is returned with id as a string instead of an integer.
    if user_id == 1:
        return {"id": "1", "name": "Alice", "email": "alice@example.com"}
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="User not found")
    return USERS[user_id]


@app.post("/api/v1/users", status_code=201)
def create_user(payload: CreateUserPayload):
    new_id = max(USERS) + 1
    user = {"id": new_id, "name": payload.name, "email": payload.email}
    USERS[new_id] = user
    return user


@app.put("/api/v1/users/{user_id}")
def update_user(user_id: int, payload: UpdateUserPayload):
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = dict(USERS[user_id])
    if payload.name is not None:
        user["name"] = payload.name
    if payload.email is not None:
        user["email"] = payload.email
    return user


@app.delete("/api/v1/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="User not found")
    del USERS[user_id]
    return Response(status_code=204)


@app.get("/api/v1/books")
def list_books():
    return {"books": list(BOOKS.values())}


@app.get("/api/v1/books/{book_id}")
def get_book(book_id: int):
    if book_id in BOOKS:
        return BOOKS[book_id]
    # Bug B: non-existent book returns 200 with an error body instead of 404.
    if book_id == 99:
        return {"detail": "Book not found"}
    raise HTTPException(status_code=404, detail="Book not found")


@app.post("/api/v1/login")
def login(payload: LoginPayload):
    if payload.username != "admin" or payload.password != "secret":
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": "mock-token-12345", "token_type": "Bearer"}


@app.get("/api/v1/me")
def get_me(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return {"id": 1, "name": "Admin", "email": "admin@example.com"}
