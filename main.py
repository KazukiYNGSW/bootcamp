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
# 巡回対象のDiscordチャンネルID（環境変数、または直接IDを入力）
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) 

# --- Google Sheets セットアップ ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)

# スプレッドシート名
SPREADSHEET_ID = "13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs"
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

# --- Discord Client セットアップ ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(CHANNEL_ID)
    
    if not channel:
        print("指定されたチャンネルが見つかりませんでした。CHANNEL_IDを確認してください。")
        await client.close()
        return

    # 直近5分（＋余裕をもって7分前まで）のメッセージを取得
    now = datetime.now(timezone.utc)
    after_time = now - timedelta(minutes=7)

    # 既にスプレッドシートにある「メッセージID」を取得して重複記録を防止
    existing_ids = sheet.col_values(5) # 5列目をID管理用に使う

    async for msg in channel.history(after=after_time, oldest_first=True):
        if msg.author.bot:
            continue
        
        # "!rec 練習内容 回数" の形式かチェック
        if msg.content.startswith("!rec"):
            parts = msg.content.split()
            if len(parts) >= 3:
                menu = parts[1]
                count = parts[2]
                msg_id_str = str(msg.id)

                # 未記録のメッセージのみ書き込み
                if msg_id_str not in existing_ids:
                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_name = msg.author.display_name
                    
                    # A列:日時, B列:名前, C列:メニュー, D列:回数, E列:メッセージID
                    sheet.append_row([jst_time, user_name, menu, count, msg_id_str])
                    print(f"記録追加: {user_name} - {menu} {count}")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)