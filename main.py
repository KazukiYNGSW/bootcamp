import os
import json
import asyncio
import unicodedata
from datetime import datetime, timedelta, timezone
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 環境変数の取得 ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_JSON = os.getenv("GOOGLE_JSON")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SPREADSHEET_ID = "13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs"

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
    channel = client.get_channel(CHANNEL_ID)
    
    if not channel:
        print("指定されたチャンネルが見つかりませんでした。")
        await client.close()
        return

    # F列（6列目）をメッセージID管理用に使用（★ここを修復したぶー）
    existing_ids = sheet.col_values(6)

    # 未記録メッセージを直近200件から古い順にチェック
    async for msg in channel.history(limit=200, oldest_first=True):
        if msg.author.bot:
            continue
        
        # 1. メッセージ全体の正規化（!rec 判定）
        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        if normalized_text.lower().startswith("!rec"):
            msg_id_str = str(msg.id)

            # 未記録のメッセージIDの場合のみ処理
            if msg_id_str not in existing_ids:
                parts = normalized_text.split()
                if len(parts) >= 3:
                    menu = parts[1]
                    count_raw = parts[2]

                    # 半角数字抽出
                    count = "".join([c for c in count_raw if c.isdigit()])
                    if not count:
                        continue

                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_id = str(msg.author.id)
                    display_name = msg.author.display_name
                    
                    # スプレッドシートへ書き込み
                    sheet.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])
                    existing_ids.append(msg_id_str)
                    print(f"記録追加: {display_name} - {menu} {count}")

                    # リアクション＆完了返信
                    try:
                        await msg.add_reaction("✅")
                    except Exception as e:
                        print(f"リアクション失敗: {e}")

                    await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー！ 「{menu}: {count}」 を記録したぶーよ🐷")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)