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
SPREADSHEET_ID = "13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs" # ←ご自身のIDを入力

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
    
    # チャンネル取得（fetch_channelで確実に取得）
   print(f"読み込んだCHANNEL_ID: {CHANNEL_ID}")
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
    except Exception as e:
        print(f"★リアルなエラー内容: {type(e).__name__} - {e}")
        await client.close()
        return

    # 直近15分前のメッセージを取得
    now = datetime.now(timezone.utc)
    after_time = now - timedelta(minutes=15)

    # F列（6列目）からメッセージIDを取得
    existing_ids = sheet.col_values(6)

    async for msg in channel.history(after=after_time, oldest_first=True):
        if msg.author.bot:
            continue
        
        # "!rec" から始まるコマンドを処理
        if msg.content.startswith("!rec"):
            parts = msg.content.split()
            if len(parts) >= 3:
                menu = parts[1]
                count = parts[2]
                msg_id_str = str(msg.id)

                # 未記録のメッセージのみ処理
                if msg_id_str not in existing_ids:
                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_id = str(msg.author.id)
                    display_name = msg.author.display_name
                    
                    # スプレッドシートに書き込み＆メモリ更新
                    sheet.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])
                    existing_ids.append(msg_id_str)
                    print(f"記録追加: {display_name} - {menu} {count}")

                    # 1. リアクション追加
                    try:
                        await msg.add_reaction("✅")
                    except Exception as e:
                        print(f"リアクション追加失敗: {e}")

                    # 2. ぶーとくんの返信メッセージ
                    try:
                        await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー 「{menu}: {count}」 を記録したぶーよ！")
                        print("返信成功だぶー！")
                    except Exception as e:
                        print(f"返信失敗: {e}")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
