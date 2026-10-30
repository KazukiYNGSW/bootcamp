import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 環境変数の取得 ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_JSON = os.getenv("GOOGLE_JSON")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SPREADSHEET_ID = "13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs" # ←ご自身のIDを入力してください

# --- Google Sheets セットアップ ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)

sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

# --- Discord Client セットアップ ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print(f"読み込んだCHANNEL_IDの値: '{CHANNEL_ID}' (型: {type(CHANNEL_ID)})")

    channel = None
    
    # 1. まず fetch_channel（Direct API）で取得を試みるだぶー
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        print(f"★fetch_channelで取得成功: {channel.name}")
    except Exception as e:
        print(f"★fetch_channel失敗エラー詳細: {e}")

    # 2. ダメなら get_channel（Cache）も試すだぶー
    if not channel:
        channel = client.get_channel(CHANNEL_ID)
        if channel:
            print(f"★get_channelで取得成功: {channel.name}")

    # どちらもダメだった場合
    if not channel:
        print("★指定されたチャンネルが見つかりませんでした。")
        await client.close()
        return

    # --- ここからメッセージ取得＆記録処理 ---
    now = datetime.now(timezone.utc)
    after_time = now - timedelta(minutes=15)
    existing_ids = sheet.col_values(6)

    async for msg in channel.history(after=after_time, oldest_first=True):
        if msg.author.bot:
            continue
        
        if msg.content.startswith("!rec"):
            parts = msg.content.split()
            if len(parts) >= 3:
                menu = parts[1]
                count = parts[2]
                msg_id_str = str(msg.id)

                if msg_id_str not in existing_ids:
                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_id = str(msg.author.id)
                    display_name = msg.author.display_name
                    
                    sheet.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])
                    existing_ids.append(msg_id_str)
                    print(f"記録追加: {display_name} - {menu} {count}")

                    try:
                        await msg.add_reaction("✅")
                    except Exception as e:
                        print(f"リアクション追加失敗: {e}")

                    try:
                        await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー 「{menu}: {count}」 を記録したぶーよ！")
                        print("返信送信成功だぶー！")
                    except Exception as e:
                        print(f"★返信送信失敗エラー: {e}")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
