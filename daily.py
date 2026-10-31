import os
import json
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 環境変数 ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_JSON = os.getenv("GOOGLE_JSON")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)
sheet_log = gc.open_by_key(SPREADSHEET_ID).sheet1

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def make_progress_bar(current, target, length=15):
    if target <= 0 or current <= 0:
        return f"{'⬜' * length} 0%"
    percent = min(1.0, current / target)
    filled = int(round(length * percent))
    empty = length - filled
    return f"{'🟩' * filled}{'⬜' * empty} {int((current / target) * 100)}%"

def get_menu_targets():
    targets = {}
    try:
        h_values = sheet_log.col_values(8)
        i_values = sheet_log.col_values(9)
        for menu, target_str in zip(h_values, i_values):
            menu_clean = menu.strip()
            if menu_clean and target_str.isdigit():
                targets[menu_clean] = int(target_str)
    except Exception as e:
        print(f"目標取得エラー: {e}")
    return targets if targets else {"PCT1": 500}

def generate_stats_text(menu_targets):
    data = sheet_log.get_all_values()
    if len(data) <= 1:
        return "まだ集計できるデータがないぶー！"

    menu_stats = {menu: {} for menu in menu_targets.keys()}
    for row in data[1:]:
        if len(row) < 5:
            continue
        display_name, menu, count_str = row[2], row[3], row[4]
        menu_clean = menu.strip()
        if menu_clean in menu_stats:
            try:
                count = int(count_str)
                menu_stats[menu_clean][display_name] = menu_stats[menu_clean].get(display_name, 0) + count
            except ValueError:
                continue

    medals = ["🥇", "🥈", "🥉"]
    report_text = "📊 **【全体 練習進捗レポート】**\n\n"
    for menu_name, target_count in menu_targets.items():
        users_data = menu_stats.get(menu_name, {})
        report_text += f"🎯 **{menu_name}** (目標: {target_count})\n"
        if users_data:
            sorted_users = sorted(users_data.items(), key=lambda x: x[1], reverse=True)
            for i, (name, cnt) in enumerate(sorted_users):
                rank = medals[i] if i < len(medals) else "👤"
                bar = make_progress_bar(cnt, target_count, length=15)
                achieve = " 🎉達成！" if cnt >= target_count else ""
                report_text += f"{rank} **{name}** : {cnt} / {target_count}\n{bar}{achieve}\n"
        else:
            report_text += "まだ記録がないぶー！\n"
        report_text += "\n"
    return report_text.strip()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        targets = get_menu_targets()
        report = generate_stats_text(targets)
        await channel.send(f"⏰ **【定期進捗レポート】**\n\n{report}")
        print("定期進捗レポート送信完了")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
