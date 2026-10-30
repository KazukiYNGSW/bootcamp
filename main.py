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

def get_menu_targets():
    """スプレッドシートの H列(メニュー) と I列(目標) を取得する関数"""
    targets = {}
    try:
        # H列(メニュー)とI列(目標)を一括取得
        h_values = sheet_log.col_values(8)  # H列
        i_values = sheet_log.col_values(9)  # I列
        
        for menu, target_str in zip(h_values, i_values):
            menu_clean = menu.strip()
            if menu_clean and target_str.isdigit():
                targets[menu_clean] = int(target_str)
    except Exception as e:
        print(f"目標メニュー取得エラー: {e}")
    
    # スプレッドシート未設定時のフォールバック (H1に旧目標値がある場合の考慮)
    if not targets:
        try:
            val = sheet_log.acell('H1').value
            if val and val.isdigit():
                targets["エイム"] = int(val)
        except:
            targets["エイム"] = 4000
            
    return targets

def make_progress_bar(current, target, length=15):
    """100%の位置（ゴール）が視覚的にわかるプログレスバーを作成する関数（15分割）"""
    if target <= 0:
        return f"{'⬜' * length} 0%"
    
    percent = min(1.0, current / target)
    filled = int(round(length * percent))
    empty = length - filled
    
    bar = "🟩" * filled + "⬜" * empty
    return f"{bar} {int((current / target) * 100)}%"

def generate_stats_text(menu_targets):
    """メニューごとの累計を集計してテキストレポートを作成する関数"""
    data = sheet_log.get_all_values()
    if len(data) <= 1:
        return "まだ集計できるデータがないぶー！"

    # メニューごとのユーザー集計データ構造: { menu_name: { display_name: total_count } }
    menu_stats = {menu: {} for menu in menu_targets.keys()}

    # 1行目はヘッダーなのでスキップ
    for row in data[1:]:
        if len(row) < 5:
            continue
        
        user_id, display_name, menu, count_str = row[1], row[2], row[3], row[4]
        menu_clean = menu.strip()

        # 現在集計対象になっているメニューのみ集計
        if menu_clean in menu_stats:
            try:
                count = int(count_str)
                menu_stats[menu_clean][display_name] = menu_stats[menu_clean].get(display_name, 0) + count
            except ValueError:
                continue

    medals = ["🥇", "🥈", "🥉"]
    report_text = "📊 **【練習進捗レポート】**\n\n"

    for menu_name, target_count in menu_targets.items():
        users_data = menu_stats.get(menu_name, {})
        report_text += f"🎯 **{menu_name}** (目標: {target_count})\n"
        
        if users_data:
            sorted_users = sorted(users_data.items(), key=lambda x: x[1], reverse=True)
            for i, (name, cnt) in enumerate(sorted_users):
                rank = medals[i] if i < len(medals) else "👤"
                bar = make_progress_bar(cnt, target_count, length=15)
                achieve = " 🎉達成！" if cnt >= target_count else ""
                report_text += f"{rank} **{name}ちゃん** : {cnt} / {target_count}\n{bar}{achieve}\n"
        else:
            report_text += "まだ記録がないぶー！\n"
        report_text += "\n"

    return report_text.strip()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("チャンネルが見つかりません")
        await client.close()
        return

    menu_targets = get_menu_targets()
    existing_ids = sheet_log.col_values(6)

    # 直近200件を取得
    messages = [m async for m in channel.history(limit=200)]

    # 1. 最新の !stats コマンドを探す
    latest_stats_msg = None
    for msg in messages:
        if msg.author.bot:
            continue
        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()
        if normalized_text.lower() == "!stats":
            msg_id_str = str(msg.id)
            if msg_id_str not in existing_ids:
                latest_stats_msg = msg
                break

    # !stats があれば返信、無ければ定時自動投稿
    report = generate_stats_text(menu_targets)
    if latest_stats_msg:
        await latest_stats_msg.reply(report)
        msg_id_str = str(latest_stats_msg.id)
        sheet_log.append_row(["", "", "", "STATS_COMMAND", "", msg_id_str])
        existing_ids.append(msg_id_str)
        try:
            await latest_stats_msg.add_reaction("✅")
        except Exception as e:
            print(f"!stats リアクション失敗: {e}")
        print("手動 !stats レポート送信完了")
    else:
        await channel.send(report)
        print("定時自動レポート送信完了")

    # 2. 既存の !rec 処理（古い順に処理）
    messages.reverse()
    for msg in messages:
        if msg.author.bot:
            continue

        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        if normalized_text.lower().startswith("!rec"):
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
                        print(f"!rec リアクション失敗: {e}")

                    await msg.reply(f"{display_name} ちゃん 報告ありがとうだぶー！ 「{menu}: {count}」 を記録したぶーよ🐷")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)