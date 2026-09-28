import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .logs import logs_router
from .storage import connect, database_path, hash_password, hash_token, initialize_database, insert_user, verify_password


SESSION_COOKIE = "intrac_session"
SESSION_SECONDS = 12 * 60 * 60
# Unknown usernames still incur the same password hashing work as existing ones.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class Role(str, Enum):
    ADMINISTRATOR = "ADMINISTRATOR"
    VERIFIER = "VERIFIER"


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    username: str
    role: Role


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role = Role.VERIFIER

    @field_validator("first_name", "last_name", "username", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value


def origin_tuple(url: str):
    parsed = urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def create_app(db_path: Path | str | None = None) -> FastAPI:
    path = Path(db_path) if db_path is not None else database_path()
    cookie_secure = os.environ.get("INTRAC_COOKIE_SECURE", "false").lower() in {"true", "1", "yes"}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(path)
        yield

    app = FastAPI(title="InTrac", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            try:
                invalid_origin = origin is not None and origin_tuple(origin) != origin_tuple(str(request.base_url))
            except ValueError:
                invalid_origin = True
            if invalid_origin or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(status_code=403, content={"detail": "Cross-origin requests are not allowed."})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exception: RequestValidationError):
        errors = []
        for error in exception.errors():
            field = str(error["loc"][-1]).replace("_", " ").capitalize()
            message = error["msg"]
            if error["type"] == "extra_forbidden":
                message = "This field is not allowed"
            elif error["type"] == "string_pattern_mismatch":
                message = "Use only letters, numbers, periods, underscores, and hyphens"
            errors.append(f"{field}: {message}.")
        return JSONResponse(status_code=422, content={"detail": " ".join(errors)})

    def current_user(request: Request) -> User:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Sign in to continue.")
        with connect(path) as connection:
            row = connection.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
                "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
                (hash_token(token), int(time.time())),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
        return User(**dict(row))

    def administrator(user: User = Depends(current_user)) -> User:
        if user.role != Role.ADMINISTRATOR:
            raise HTTPException(status_code=403, detail="Only administrators can create users.")
        return user

    @app.post("/api/auth/login", response_model=User)
    def login(credentials: Login, request: Request, response: Response):
        with connect(path) as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (credentials.username,)).fetchone()
        encoded = row["password_hash"] if row is not None else DUMMY_PASSWORD_HASH
        valid = verify_password(credentials.password, encoded)
        if row is None or not valid:
            raise HTTPException(status_code=401, detail="Incorrect username or password.")

        token = secrets.token_urlsafe(32)
        with connect(path) as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            previous_token = request.cookies.get(SESSION_COOKIE)
            if previous_token:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(previous_token),))
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (hash_token(token), row["id"], int(time.time()) + SESSION_SECONDS),
            )
        response.set_cookie(
            SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
            secure=cookie_secure or request.url.scheme == "https", samesite="lax", path="/"
        )
        return User(**dict(row))

    @app.get("/api/auth/me", response_model=User)
    def me(user: User = Depends(current_user)):
        return user

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            with connect(path) as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
        response = Response(status_code=204)
        response.delete_cookie(
            SESSION_COOKIE, path="/", httponly=True,
            secure=cookie_secure or request.url.scheme == "https", samesite="lax"
        )
        return response

    @app.post("/api/users", status_code=201, response_model=User)
    def create_user(new_user: UserCreate, _: User = Depends(administrator)):
        try:
            user = insert_user(path, **new_user.model_dump())
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="That username is already in use.") from None
        return User(**user)

    app.include_router(logs_router(path, current_user))
    return app


app = create_app()
