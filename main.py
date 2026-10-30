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
    return 500  # デフォルト目標値

def make_progress_bar(current, target, length=10):
    """コントラストの高い絵文字プログレスバーを作成する関数"""
    if target <= 0:
        return "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛ 0%"
    percent = min(1.0, current / target)
    filled = int(round(length * percent))
    bar = "🟩" * filled + "⬛" * (length - filled)
    return f"{bar} {int((current / target) * 100)}%"

def generate_stats_text(target_count):
    """スプレッドシートのデータを集計してテキストレポートを作成する関数"""
    data = sheet_log.get_all_values()
    if len(data) <= 1:
        return "まだ集計できるデータがないぶー！"

    # JST現在日時
    now = datetime.now(timezone(timedelta(hours=9)))
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    week_counts = {}
    month_counts = {}

    # 1行目はヘッダーなのでスキップ
    for row in data[1:]:
        if len(row) < 5:
            continue
        
        date_str, user_id, display_name, menu, count_str = row[0], row[1], row[2], row[3], row[4]
        
        try:
            count = int(count_str)
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=9)))
        except ValueError:
            continue

        # 今週分集計
        if dt >= start_of_week:
            week_counts[display_name] = week_counts.get(display_name, 0) + count

        # 今月分集計
        if dt >= start_of_month:
            month_counts[display_name] = month_counts.get(display_name, 0) + count

    medals = ["🥇", "🥈", "🥉"]
    
    # 今週の集計テキスト
    week_text = f"📅 **今週の進捗** (目標: {target_count})\n"
    if week_counts:
        sorted_week = sorted(week_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (name, cnt) in enumerate(sorted_week):
            rank = medals[i] if i < len(medals) else "👤"
            bar = make_progress_bar(cnt, target_count)
            achieve = " 🎉達成！" if cnt >= target_count else ""
            week_text += f"{rank} **{name}ちゃん** : {cnt} / {target_count}\n{bar}{achieve}\n"
    else:
        week_text += "今週の記録はまだないぶー！\n"

    # 今月の集計テキスト
    month_text = f"\n🗓 **今月の進捗** (目標: {target_count})\n"
    if month_counts:
        sorted_month = sorted(month_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (name, cnt) in enumerate(sorted_month):
            rank = medals[i] if i < len(medals) else "👤"
            bar = make_progress_bar(cnt, target_count)
            achieve = " 🎉達成！" if cnt >= target_count else ""
            month_text += f"{rank} **{name}ちゃん** : {cnt} / {target_count}\n{bar}{achieve}\n"
    else:
        month_text += "今月の記録はまだないぶー！\n"

    return f"📊 **【練習進捗レポート】**\n\n{week_text}{month_text}"

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

    # 直近200件を取得（古い順）
    messages = [m async for m in channel.history(limit=200)]
    messages.reverse()

    for msg in messages:
        if msg.author.bot:
            continue

        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        # Bot自身がすでに「✅」リアクションを付けたメッセージか判定
        has_bot_reaction = False
        for reaction in msg.reactions:
            async for user in reaction.users():
                if user.id == client.user.id:
                    has_bot_reaction = True
                    break
            if has_bot_reaction:
                break

        # !stats コマンド処理（未処理のものだけ）
        if normalized_text.lower() == "!stats":
            if not has_bot_reaction:
                report = generate_stats_text(target_count)
                await msg.reply(report)
                try:
                    await msg.add_reaction("✅")
                except Exception as e:
                    print(f"リアクション失敗: {e}")
                print("レポート送信完了")

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