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
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

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

def append_to_first_columns(row_data):
    """A〜F列の最終行を正確に取得して追記する関数"""
    col_a = sheet_log.col_values(1)
    next_row = len(col_a) + 1
    cell_range = f"A{next_row}:F{next_row}"
    sheet_log.update(cell_range, [row_data])

def get_menu_targets():
    """スプレッドシートの H列(メニュー) と I列(目標) を取得する関数"""
    targets = {}
    try:
        h_values = sheet_log.col_values(8)  # H列
        i_values = sheet_log.col_values(9)  # I列
        
        for menu, target_str in zip(h_values, i_values):
            menu_clean = menu.strip()
            if menu_clean and target_str.isdigit():
                targets[menu_clean] = int(target_str)
    except Exception as e:
        print(f"目標メニュー取得エラー: {e}")
    
    if not targets:
        try:
            val = sheet_log.acell('I1').value
            if val and val.isdigit():
                targets["PCT1"] = int(val)
        except:
            targets["PCT1"] = 500
            
    return targets

def make_progress_bar(current, target, length=15):
    """100%の位置（ゴール）が視覚的にわかるプログレスバーを作成する関数（15分割）"""
    if target <= 0 or current <= 0:
        return f"{'⬜' * length} 0%"
    
    percent = min(1.0, current / target)
    filled = int(round(length * percent))
    empty = length - filled
    
    bar = "🟩" * filled + "⬜" * empty
    return f"{bar} {int((current / target) * 100)}%"

def generate_stats_text(menu_targets, target_user_name=None):
    """
    集計テキストを作成する関数
    target_user_name が指定されていれば『その人のみ』の個人スタッツを作成
    指定がなければ『全員分』のランキングスタッツを作成
    """
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

    # --- 個人スタッツ（!rec 報告時用）---
    if target_user_name:
        report_text = f"📊 **{target_user_name}ちゃんの現在の進捗だぶー！**\n"
        has_data = False
        for menu_name, target_count in menu_targets.items():
            user_cnt = menu_stats.get(menu_name, {}).get(target_user_name, 0)
            if user_cnt != 0:
                has_data = True
                bar = make_progress_bar(user_cnt, target_count, length=15)
                achieve = " 🎉目標達成！" if user_cnt >= target_count else ""
                report_text += f"\n🎯 **{menu_name}** : {user_cnt} / {target_count}\n{bar}{achieve}"
        if not has_data:
            report_text += "\nまだ集計対象メニューの記録がないぶー！"
        return report_text.strip()

    # --- 全員分スタッツ（!stats ＆ 定時配信時用）---
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
    if not channel:
        print("チャンネルが見つかりません")
        await client.close()
        return

    menu_targets = get_menu_targets()
    existing_ids = sheet_log.col_values(6)  # F列（メッセージID）

    now_jst = datetime.now(timezone(timedelta(hours=9)))

    # 直近50件を取得
    messages = [m async for m in channel.history(limit=50)]

    # 1. 未処理の !rec コマンドを処理（古い順）
    messages_old_first = list(reversed(messages))
    for msg in messages_old_first:
        if msg.author.bot:
            continue

        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()

        if normalized_text.lower().startswith("!rec"):
            msg_id_str = str(msg.id)
            
            # 【重要】過去に既にシートに記録されているメッセージはスキップ
            if msg_id_str in existing_ids:
                continue

            # 【重要】Botがリアクション「✅」をすでに付けているメッセージも重複とみなしてスキップ
            if any(r.emoji == "✅" and r.me for r in msg.reactions):
                continue

            parts = normalized_text.split()
            if len(parts) >= 3:
                menu = parts[1]
                count_raw = parts[2]
                
                count_clean = "".join([c for i, c in enumerate(count_raw) if c.isdigit() or (i == 0 and c == '-')])
                if not count_clean or count_clean == "-":
                    continue

                count = int(count_clean)

                jst_time = msg.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
                user_id = str(msg.author.id)
                display_name = msg.author.display_name

                # スプレッドシートに追記
                append_to_first_columns([jst_time, user_id, display_name, menu, str(count), msg_id_str])
                existing_ids.append(msg_id_str)

                try:
                    await msg.add_reaction("✅")
                except Exception as e:
                    print(f"!rec リアクション失敗: {e}")

                user_personal_stats = generate_stats_text(menu_targets, target_user_name=display_name)
                reply_msg = (
                    f"{display_name} ちゃん 報告ありがとうだぶー！ 「{menu}: {count}」 を記録したぶーよ🐷\n\n"
                    f"{user_personal_stats}"
                )
                await msg.reply(reply_msg)

    # 2. 最新の !stats コマンド処理
    latest_stats_msg = None
    for msg in messages:
        if msg.author.bot:
            continue
        normalized_text = unicodedata.normalize('NFKC', msg.content).strip()
        if normalized_text.lower() == "!stats":
            msg_id_str = str(msg.id)
            if msg_id_str not in existing_ids and not any(r.emoji == "✅" and r.me for r in msg.reactions):
                latest_stats_msg = msg
                break

    if latest_stats_msg:
        all_report = generate_stats_text(menu_targets)
        await latest_stats_msg.reply(all_report)
        msg_id_str = str(latest_stats_msg.id)
        append_to_first_columns(["", "", "", "STATS_COMMAND", "", msg_id_str])
        existing_ids.append(msg_id_str)
        try:
            await latest_stats_msg.add_reaction("✅")
        except Exception as e:
            print(f"!stats リアクション失敗: {e}")
        print("手動 !stats レポート送信完了")

    # 3. 定期配信・GAS起動時レポート処理（本日まだ未送信の場合に自動出力）
    today_str = now_jst.strftime("%Y-%m-%d")
    daily_sent_flag = f"DAILY_STATS_{today_str}"

    if daily_sent_flag not in existing_ids:
        append_to_first_columns([now_jst.strftime("%Y-%m-%d %H:%M"), "", "BOT", "DAILY_STATS", "", daily_sent_flag])
        existing_ids.append(daily_sent_flag)
        
        all_report = generate_stats_text(menu_targets)
        await channel.send(f"⏰ **【定期進捗レポート】**\n\n{all_report}")
        print("定時/GAS起動進捗レポート送信完了")

    print("処理完了。終了します。")
    await client.close()

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
