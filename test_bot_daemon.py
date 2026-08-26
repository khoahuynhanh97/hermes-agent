
import asyncio
from hermes.channels.gateway.platforms.telegram.bot import app

async def run_bot():
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print('BOT DAEMON STARTED SUCCESSFULLY AND POLLING!')
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(run_bot())
