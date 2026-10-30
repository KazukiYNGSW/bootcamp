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

    # 直近7分前のメッセージを取得
    now = datetime.now(timezone.utc)
    after_time = now - timedelta(minutes=7)

    # F列（6列目）をメッセージID管理用に使用
    existing_ids = sheet.col_values(6)

    async for msg in channel.history(after=after_time, oldest_first=True):
        if msg.author.bot:
            continue
        
        # 1. メッセージ全体を半角正規化
        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        # "!rec" から始まるコマンドを処理
        if normalized_text.lower().startswith("!rec"):
            parts = normalized_text.split()
            if len(parts) >= 3:
                # メニュー名も確実に半角変換（英数など）
                menu = unicodedata.normalize('NFKC', parts[1])
                
                # 回数・数値部分を半角変換して数字のみ抽出
                count_raw = unicodedata.normalize('NFKC', parts[2])
                count = "".join([c for c in count_raw if c.isdigit()])
                
                if not count:
                    continue # 数字がない場合はスキップ

                msg_id_str = str(msg.id)

                # 未記録のメッセージのみ処理
                if msg_id_str not in existing_ids:
                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_id = str(msg.author.id)
                    display_name = msg.author.display_name
                    
                    # 半角化された count / menu でスプレッドシートに書き込み
                    sheet.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])
                    existing_ids.append(msg_id_str)
                    print(f"記録追加: {display_name} - {menu} {count}")

                    # 1. リアクション追加
                    try:
                        await msg.add_reaction("✅")
                    except Exception as e:
                        print(f"リアクション追加失敗: {e}")

                    # 2. ぶーとくんの完了返信
                    await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー 「{menu}: {count}」 を記録したぶーよ！")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
