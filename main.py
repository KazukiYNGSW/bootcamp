import os
import json
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 環境変数 & Google Sheets 設定 ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_JSON = os.getenv("GOOGLE_JSON")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SPREADSHEET_ID = "13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# --- ボタンとUIの定義 ---
class RecordView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # ずっと消えないボタンパネル

    # メニュー選択（ドロップダウン）
    @discord.ui.select(
        placeholder="練習メニューを選んでね！",
        options=[
            discord.SelectOption(label="エイム", value="エイム", description="エイム練習の記録"),
            discord.SelectOption(label="建築", value="建築", description="建築練習の記録"),
            discord.SelectOption(label="編集", value="編集", description="編集練習の記録"),
        ]
    )
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 選択したメニューを一時保持
        self.selected_menu = select.values[0]
        await interaction.response.send_message(f"「{self.selected_menu}」を選んだぶー！下の回数・時間ボタンを押してね！", ephemeral=True)

    # 回数・時間のボタン（10回 / 30分 / 60分 など自由に追加可能）
    @discord.ui.button(label="10", style=discord.ButtonStyle.primary)
    async def button_10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_record(interaction, count="10")

    @discord.ui.button(label="30", style=discord.ButtonStyle.primary)
    async def button_30(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_record(interaction, count="30")

    @discord.ui.button(label="60", style=discord.ButtonStyle.primary)
    async def button_60(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_record(interaction, count="60")

    # スプレッドシート保存処理
    async def save_record(self, interaction: discord.Interaction, count: str):
        menu = getattr(self, 'selected_menu', 'エイム') # デフォルトはエイム
        display_name = interaction.user.display_name
        user_id = str(interaction.user.id)
        jst_time = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        msg_id_str = str(interaction.id)

        # スプレッドシートへ書き込み
        sheet.append_row([jst_time, user_id, display_name, menu, count, msg_id_str])

        # 完了メッセージを返信（他の人にも見えるように送信）
        await interaction.response.send_message(
            f"{display_name} ちゃん 報告ありがとうだぶー 「{menu}: {count}」 を記録したぶーよ！"
        )

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        # 起動時にチャンネルへパネルを設置（または更新）
        await channel.send("【ボットくん練習記録パネル】\nメニューを選んでボタンを押すだけで記録できるぶー！", view=RecordView())

client.run(DISCORD_TOKEN)