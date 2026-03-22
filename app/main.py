"""
Main entry point: FastAPI app + Aiogram bot running together.
Bot uses webhook mode in production (Railway), polling in dev.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from app.config import settings
from app.db.session import init_db, AsyncSessionLocal
from app.services.routing_service import seed_default_scenarios

# Bot & Dispatcher
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Register middlewares
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.role import RoleMiddleware
dp.update.middleware(DbSessionMiddleware())
dp.update.middleware(RoleMiddleware())

# Register routers
from app.bot.handlers import common, user, executor, admin as admin_handler
dp.include_router(common.router)
dp.include_router(admin_handler.router)
dp.include_router(executor.router)
dp.include_router(user.router)   # User router LAST (catches all text)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting HelpDesk...")
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_default_scenarios(db)

    if settings.webhook_url:
        webhook = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"
        await bot.set_webhook(webhook, drop_pending_updates=True)
        logger.info(f"Webhook set: {webhook}")
    else:
        # Start polling in background for local dev
        logger.info("No WEBHOOK_URL — starting polling")
        asyncio.create_task(dp.start_polling(bot, skip_updates=True))

    yield

    # Shutdown
    if settings.webhook_url:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("Shutdown complete.")


app = FastAPI(title="IT HelpDesk", lifespan=lifespan)

# Static files
import os
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# ── Webhook endpoint ───────────────────────────────────────────────────────────
@app.post(settings.webhook_path)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}


# ── Web Console ────────────────────────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin/index.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return HTMLResponse(
        "<meta http-equiv='refresh' content='0; url=/admin'>"
        "<p>Redirecting to <a href='/admin'>Admin Panel</a>...</p>"
    )

# ── API Routers ────────────────────────────────────────────────────────────────
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.users_routes import users_router, routes_router

app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(users_router)
app.include_router(routes_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
