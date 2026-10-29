import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# 設定項目
# ==========================================
DISCORD_TOKEN = 'MTUxNDk3MjYzMzE3ODA0NjQ5NA.G52LrF.dNvfxt_GkKNa1eDRgTc4AKiSTvVA0IanZ-eoNY'      # 保存したBotのトークン
SPREADSHEET_ID = '13TnkcrRnrvIQq6bQT339FQSMq7foSZo35neuz47ZhAs'        # スプレッドシートのID
JSON_KEY_FILE = 'credentials.json'             # APIの鍵ファイル名

# ==========================================
# Googleスプレッドシートの接続設定
# ==========================================
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# ==========================================
# Discord Botの設定
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Bot is ready to record!')

@bot.event
async def on_message(message):
    # Bot自身の発言は無視
    if message.author.bot:
        return

    # コマンド判定（例: !rec エイム 50 や !rec 100 など）
    if message.content.startswith('!rec'):
        args = message.content.split()[1:]
        
        if not args:
            await message.channel.send('❌ 使い方: `!rec [メニュー名] [回数]` または `!rec [回数]`\n例: `!rec エイム 50` / `!rec 100`')
            return

        # パラメータの解析
        if len(args) == 1:
            # 数字だけ入力された場合 (!rec 100)
            menu_name = '練習'
            count_str = args[0]
        else:
            # メニュー名と数字の両方 (!rec エイム 50)
            menu_name = args[0]
            count_str = args[1]

        # 数字チェック
        if not count_str.isdigit():
            await message.channel.send('❌ 回数は半角の数字で入力してね！ 例: `!rec エイム 50`')
            return

        count = int(count_str)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_id = str(message.author.id)
        display_name = message.author.display_name

        try:
            # スプレッドシートの末尾に追記 (日付, ユーザーID, 表示名, メニュー名, 回数)
            sheet.append_row([now, user_id, display_name, menu_name, count])
            
            await message.channel.send(
                f'✅ **{display_name}** さんの記録を保存したよ！\n'
                f'・メニュー: `{menu_name}`\n'
                f'・回数: `{count}` 回'
            )
        except Exception as e:
            print(f'Error writing to sheet: {e}')
            await message.channel.send('❌ スプレッドシートへの記録中にエラーが発生しました。')

    await bot.process_commands(message)

# Bot起動
bot.run(DISCORD_TOKEN)