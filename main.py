import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.config import config
from database.database import db
from handlers import common, markets, wallets
from services.background import start_background_tasks

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def main():
    await db.create_tables()
    
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(common.router)
    dp.include_router(markets.router)
    dp.include_router(wallets.router)

    await start_background_tasks(bot)

    logging.info("Bot is starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")