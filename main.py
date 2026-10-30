import os
import json
import asyncio
import unicodedata
from datetime import datetime, timedelta, timezone
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import matplotlib
matplotlib.use('Agg') # サーバー環境用（画面描画なし）の設定
import matplotlib.pyplot as plt

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

workbook = gc.open_by_key(SPREADSHEET_ID)
sheet_log = workbook.sheet1  # ログ記録シート

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def get_target_count():
    """スプレッドシートの H1 セルから目標値を取得する関数"""
    try:
        val = sheet_log.acell('H1').value
        if val and val.isdigit():
            return int(val)
    except Exception as e:
        print(f"目標値取得エラー: {e}")
    return 1000  # デフォルト目標値

def generate_stats_image(target_count):
    """スプレッドシートから集計して今週・今月のグラフ画像を生成する関数"""
    data = sheet_log.get_all_values()
    if len(data) <= 1:
        print("集計データが少なすぎます")
        return None

    # DataFrame化
    df = pd.DataFrame(data[1:], columns=['datetime', 'user_id', 'name', 'menu', 'count', 'msg_id'])
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
    df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0)

    # 現在日時（JST）
    now = datetime.now(timezone(timedelta(hours=9)))
    
    # 今週の開始日 (月曜日) と今月の開始日 (1日)
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # タイムゾーン補正してフィルタリング
    df['datetime_naive'] = df['datetime'].dt.tz_localize(None)
    df_week = df[df['datetime_naive'] >= start_of_week.replace(tzinfo=None)]
    df_month = df[df['datetime_naive'] >= start_of_month.replace(tzinfo=None)]

    # ユーザー別集計
    week_stats = df_week.groupby('name')['count'].sum()
    month_stats = df_month.groupby('name')['count'].sum()

    # グラフ描画
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # 今週のグラフ
    if not week_stats.empty:
        ax1.barh(week_stats.index, week_stats.values, color='skyblue')
        ax1.axvline(target_count, color='red', linestyle='--', label=f'Target ({target_count})')
        ax1.set_title('Weekly Stats')
        ax1.set_xlabel('Count')
        ax1.legend()
    else:
        ax1.text(0.5, 0.5, 'No Data (This Week)', ha='center', va='center')

    # 今月のグラフ
    if not month_stats.empty:
        ax2.barh(month_stats.index, month_stats.values, color='lightgreen')
        ax2.axvline(target_count, color='red', linestyle='--', label=f'Target ({target_count})')
        ax2.set_title('Monthly Stats')
        ax2.set_xlabel('Count')
        ax2.legend()
    else:
        ax2.text(0.5, 0.5, 'No Data (This Month)', ha='center', va='center')

    plt.tight_layout()
    image_path = 'stats.png'
    plt.savefig(image_path)
    plt.close()
    print("グラフ画像の生成完了:", image_path)
    return image_path

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("チャンネルが見つかりません")
        await client.close()
        return

    target_count = get_target_count()
    existing_ids = sheet_log.col_values(6)

    # 直近200件を取得（新しい順ではなく処理しやすいように順序確認）
    messages = [m async for m in channel.history(limit=200)]
    messages.reverse() # 古い順に並び替え

    for msg in messages:
        if msg.author.bot:
            continue

        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        # !stats コマンド処理
        if normalized_text.lower() == "!stats":
            print("!stats コマンドを検知しました")
            image_path = generate_stats_image(target_count)
            if image_path and os.path.exists(image_path):
                await msg.reply(f"📊 【練習進捗レポート】共通目標: {target_count}\n今週＆今月の集計結果だぶー！", file=discord.File(image_path))
                print("グラフ送信成功")
            else:
                await msg.reply("まだ集計できるデータがないぶー！")

        # 既存の !rec 処理
        elif normalized_text.lower().startswith("!rec"):
            msg_id_str = str(msg.id)
            if msg_id_str not in existing_ids:
                parts = normalized_text.split()
                if len(parts) >= 3:
                    menu = parts[1]
                    count_raw = parts[2]
                    count = "".join([c for c in count_raw if c.isdigit()])
                    if not count:
                        continue

                    jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                    user_id = str(msg.author.id)
                    display_name = msg.author.display_name

                    sheet_log.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])
                    existing_ids.append(msg_id_str)

                    try:
                        await msg.add_reaction("✅")
                    except Exception as e:
                        print(f"リアクション失敗: {e}")

                    await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー！ 「{menu}: {count}」 を記録したぶーよ🐷")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)