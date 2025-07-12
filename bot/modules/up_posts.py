from json import loads as jloads
from os import path as ospath, execl
from sys import executable
from bot import bot
from aiohttp import ClientSession
from bot import Var, bot, ffQueue
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler
from pyrogram import filters
from bot.core.text_utils import TextEditor
from bot.core.reporter import rep
from bot.core.func_utils import decode, is_fsubbed, get_fsubs, editMessage, sendMessage, new_task, convertTime, getfeed
from asyncio import sleep as asleep, gather
from pyrogram.filters import command, private, user
from pyrogram import filters
import time
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.types import Message
from pyrogram.types import Message
import subprocess
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified

from bot import bot, bot_loop, Var, ani_cache

DB_URI = "mongodb+srv://nitinkumardhundhara:DARKXSIDE78@cluster0.wdive.mongodb.net/?retryWrites=true&w=majority"
mongo_client = AsyncIOMotorClient(DB_URI)
db = mongo_client['AutoAniOngoing']

def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

# Function to measure DB response time
async def get_db_response_time() -> float:
    start = time.time()
    # Perform a simple query
    await db.command("ping")
    end = time.time()
    return round((end - start) * 1000, 2)  # DB response time in milliseconds

async def get_ping(bot: bot) -> float:
    start = time.time()
    await bot.get_me()  # Simple call to measure round-trip time
    end = time.time()
    return round((end - start) * 1000, 2)  

@bot.on_message(filters.command('ping') & user(Var.ADMINS))
@new_task
async def stats(client, message):
    now = datetime.now()
    delta = now - bot.uptime
    uptime = get_readable_time(delta.seconds)

    ping = await get_ping(bot)

    db_response_time = await get_db_response_time()

    stats_text = (
        f"Bot Uptime: {uptime}\n"
        f"Ping: {ping} ms\n"
        f"Database Response Time: {db_response_time} ms\n"
    )

    await message.reply(stats_text)

@bot.on_message(filters.command('shell') & private & user(Var.ADMINS))
@new_task
async def shell(client, message):
    message = update.effective_message
    cmd = message.text.split(" ", 1)
    if len(cmd) == 1:
        message.reply_text("No command to execute was given.")
        return
    cmd = cmd[1]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
    )
    stdout, stderr = process.communicate()
    reply = ""
    stderr = stderr.decode()
    stdout = stdout.decode()
    if stdout:
        reply += f"*ᴘᴀʀᴀᴅᴏx \n stdout*\n`{stdout}`\n"
        LOGGER.info(f"Shell - {cmd} - {stdout}")
    if stderr:
        reply += f"*ᴘᴀʀᴀᴅᴏx \n stdou*\n`{stderr}`\n"
        LOGGER.error(f"Shell - {cmd} - {stderr}")
    if len(reply) > 3000:
        with open("shell_output.txt", "w") as file:
            file.write(reply)
        with open("shell_output.txt", "rb") as doc:
            context.bot.send_document(
                document=doc,
                filename=doc.name,
                reply_to_message_id=message.message_id,
                chat_id=message.chat_id,
            )
    else:
        message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.command("ongoing"))
@new_task
async def ongoing_animes(client, message):
    if Var.SEND_SCHEDULE:
        try:
            async with ClientSession() as ses:
                res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
                aniContent = jloads(await res.text())["schedule"]

            text = "<b>📆 Today's Anime Releases Schedule [IST]</b>\n\n"
            for i in aniContent:
                aname = TextEditor(i["title"])
                await aname.load_anilist()
                text += f''' <a href="https://subsplease.org/shows/{i['page']}">{aname.adata.get('title', {}).get('english') or i['title']}</a>\n    • <b>Time</b> : {i["time"]} hrs\n\n'''

            # Sending the message to the user
            await message.reply_text(text)

        except Exception as err:
            await message.reply_text(f"Error: {str(err)}")

    if not ffQueue.empty():
        await ffQueue.join()
    await rep.report("Auto Restarting...!!!", "info")
    execl(executable, executable, "-m", "bot")

async def update_shdr(name, link):
    if TD_SCHR is not None:
        TD_lines = TD_SCHR.text.split('\n')
        for i, line in enumerate(TD_lines):
            if line.startswith(f"📌 {name}"):
                TD_lines[i+2] = f"    • **Status :** ✅ __Uploaded__\n    • **Link :** {link}"
        await TD_SCHR.edit("\n".join(TD_lines))


async def upcoming_animes():
    if Var.SEND_SCHEDULE:
        try:
            async with ClientSession() as ses:
                res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
                aniContent = jloads(await res.text())["schedule"]
            text = "<b>📆 Today's Anime Releases Schedule [IST]</b>\n\n"
            for i in aniContent:
                aname = TextEditor(i["title"])
                await aname.load_anilist()
                text += f''' <a href="https://subsplease.org/shows/{i['page']}">{aname.adata.get('title', {}).get('english') or i['title']}</a>\n    • <b>Time</b> : {i["time"]} hrs\n\n'''
            TD_SCHR = await bot.send_message(Var.MAIN_CHANNEL, text)
            await (await TD_SCHR.pin()).delete()
        except Exception as err:
            await rep.report(str(err), "error")
    if not ffQueue.empty():
        await ffQueue.join()
    await rep.report("Auto Restarting..!!", "info")
    execl(executable, executable, "-m", "bot")

async def update_shdr(name, link):
    if TD_SCHR is not None:
        TD_lines = TD_SCHR.text.split('\n')
        for i, line in enumerate(TD_lines):
            if line.startswith(f"📌 {name}"):
                TD_lines[i+2] = f"    • **Status :** ✅ __Uploaded__\n    • **Link :** {link}"
        await TD_SCHR.edit("\n".join(TD_lines))
