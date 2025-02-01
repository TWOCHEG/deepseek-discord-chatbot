import disnake
from disnake.ext import commands
import asyncio
from langdetect import detect
from disnake import Localized, Locale
import json
import aiohttp
from bs4 import BeautifulSoup
import re
import requests
from googlesearch import search


class ChatBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.message_limit = 2000

        self.chats = {}

        self.model = 'deepseek/deepseek-chat'
        self.reasoning_model = 'deepseek/deepseek-r1:free'
        self.openrouter_api_key = "YOUR_OPENROUTER_API_KEY"

    def fetch_webpage_text(self, url):
        """Получает текстовое содержимое веб-страницы."""
        try:
            response = requests.get(
                url, 
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, 
                timeout=10
            )
            response.raise_for_status()

            # Проверяем, есть ли блокировка по JavaScript
            if "JavaScript" in response.text or "captcha" in response.text.lower():
                return False  # Пропускаем такие сайты
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем скрипты и стили
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()
            
            # Получаем текст
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)  # Убираем лишние пробелы
            return text[:997] + '...' if len(text) > 1000 else text
        except Exception:
            return False

    def search_and_extract(self, query, num_results=3):
        """Ищет в Google и извлекает текст с сайтов."""
        results = []
        
        for link in search(query, num_results=num_results):
            text = self.fetch_webpage_text(link)
            if text:
                results.append(f"**website:** {link}\n**extracted text:** {text}\n")
                
        if results:
            return "\n".join(results)
        else:
            return 'not found'

    async def components(self, user_id):
        return [
            disnake.ui.Button(
                label='🔎',
                style=disnake.ButtonStyle.blurple if self.chats[user_id]['web_search'] else disnake.ButtonStyle.grey,
                custom_id=f'chatbot_websearch_{user_id}'
            ),
            disnake.ui.Button(
                label='R1',
                style=disnake.ButtonStyle.blurple if self.chats[user_id]['r1'] else disnake.ButtonStyle.grey,
                custom_id=f'chatbot_r1_{user_id}'
            ),
            disnake.ui.Button(
                label='⬜',
                style=disnake.ButtonStyle.red,
                custom_id=f'chatbot_stop_{user_id}'
            )
        ]
        
    async def check(self, message):
        guild = message.guild
        ctx = message.content

        if message.guild:
            if message.channel.is_nsfw():
                return False
        
        if (ctx.replace(' ', '') if ' ' in ctx else ctx) == self.bot.user.mention:
            return False
        
        if not message.guild and not message.author.bot:
            return True

        if self.bot.user.mentioned_in(message):
            if message.mentions:
                if len(message.mentions) > 1:
                    return False

                required_permissions = disnake.Permissions(
                    view_channel=True,
                    send_messages=True
                )
                guild = message.guild

                if not guild.me.guild_permissions.is_superset(required_permissions):
                    return False

                return True
            else:
                return True
        return False

    async def create_chat(self, user_id):
        self.chats[user_id] = {
            "messages": [],
            "web_search": False,
            "r1": False,
            "in_progress": False,
            "embeds": [],
            "content": None,
            "thinks": None,
            "stop": False
        }

    async def generating(self, user_id, content, lange):
        self.chats[user_id]['in_progress'] = True
        self.chats[user_id]['messages'].append({"role": "user", "content": content})

        if self.chats[user_id]['web_search']:
            result = self.search_and_extract(content)
            self.chats[user_id]['messages'].append({"role": "user", "system": "web search results:\n" + str(result)})
            self.chats[user_id]['embeds'].append(
                disnake.Embed(
                    title='веб поиск' if lange == 'ru' else 'web search',
                    description=str(result)[:1997] + '...' if len(result) > 2000 else str(result)
                ).set_thumbnail('https://lh3.googleusercontent.com/COxitqgJr1sJnIDe8-jiKhxDx1FrYbtRHKJ9z_hELisAlapwE9LUPh6fcXIfb5vwpbMl4xl9H9TRFPc5NOO8Sb3VSgIBrfRYvW6cUA')
            )

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.reasoning_model if self.chats[user_id]['r1'] else self.model,
            "messages": self.chats[user_id]['messages'],
            "include_reasoning": self.chats[user_id]['r1'],
            "stream": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    async for line in response.content:
                        if self.chats[user_id]['stop']:
                            self.chats[user_id]['stop'] = False
                            break

                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line.startswith('data:'):
                            try:
                                json_data = json.loads(decoded_line[5:])
                                if 'error' in json_data:
                                    self.chats[user_id]['content'] = 'error: ' + json_data['error']['message']
                                    break

                                content = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                reasoning = json_data.get("choices", [{}])[0].get("delta", {}).get("reasoning", "")

                                if content:
                                    self.chats[user_id]['content'] = (self.chats[user_id]['content'] or "") + content
                                if reasoning:
                                    self.chats[user_id]['thinks'] = (self.chats[user_id]['thinks'] or "") + reasoning

                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            self.chats[user_id]['content'] = f"error: {e}"

        self.chats[user_id]['messages'].append(
            {
                "role": "assistant", "content": (
                    self.chats[user_id]['content'] + 
                    'system: your reasoning:\n' + str(self.chats[user_id]['thinks']) if self.chats[user_id]['content'] else self.chats[user_id]['content']
                )
            }
        )
        self.chats[user_id]['in_progress'] = False

    async def message_edit(self, message, user_id, lange, bot_message):
        if self.chats[user_id]['r1']:
            await bot_message.edit(
                (str(self.chats[user_id]['content'])[:2000] if len(self.chats[user_id]['content']) > 2000 else str(self.chats[user_id]['content'])) if self.chats[user_id]['content'] else '...', 
                embeds=[
                    disnake.Embed(
                        title='глубокое размышление' if lange == 'ru' else 'deep think',
                        description=(str(self.chats[user_id]['thinks'])[:2000] if len(self.chats[user_id]['thinks']) > 2000 else str(self.chats[user_id]['thinks'])) if (self.chats[user_id]['thinks'] and not str(self.chats[user_id]['thinks']).replace(' ', '') == '') else '...'
                    ),
                    *self.chats[user_id]["embeds"]
                ],
                components=await self.components(user_id)
            )
        else:
            await bot_message.edit(
                (str(self.chats[user_id]['content'])[:2000] if len(self.chats[user_id]['content']) > 2000 else str(self.chats[user_id]['content'])) if self.chats[user_id]['content'] else '...', 
                embeds=self.chats[user_id]["embeds"], 
                components=await self.components(user_id)
            )

    async def message(self, user_id, message, lange):
        while self.chats[user_id]["content"] is None and self.chats[user_id]["thinks"] is None:
            await asyncio.sleep(1)
        bot_message = await message.channel.send('...', reference=message)
        
        while self.chats[user_id]['in_progress']:
            await self.message_edit(message, user_id, lange, bot_message)

            await asyncio.sleep(1)

        await self.message_edit(message, user_id, lange, bot_message)

        self.chats[user_id]['content'] = None
        self.chats[user_id]['thinks'] = None
        self.chats[user_id]['embeds'] = []

    async def starter(self, user_id, message, lange, content):
        if not user_id in self.chats:
            await self.create_chat(user_id)

        if self.chats[user_id]["in_progress"]:
            while self.chats[user_id]["in_progress"]:
                await asyncio.sleep(1)

        asyncio.create_task(self.generating(user_id, content, lange))
        asyncio.create_task(self.message(user_id, message, lange))

    @commands.Cog.listener()
    async def on_message(self, message):
        user_id = message.author.id
        content = message.content

        if self.bot.user.mention:
            content = content.replace(self.bot.user.mention, '')

        if await self.check(message):

            try:
                lange = detect(content)
            except Exception:
                lange = 'eu'

            async with message.channel.typing():
                try:
                    await self.starter(user_id, message, lange, content)
                except Exception as e:
                    await message.channel.send(
                        embed=disnake.Embed(
                            title='ошибка' if lange == 'ru' else 'error',
                            description=e,
                            color=disnake.Color.red()
                        ),
                        reference=message
                    )
                    if user_id in self.chats:
                        del self.chats[user_id]
            return True
        
        return False
        
    @commands.slash_command(
        name=Localized(
            'chat_bot',
            data={
                Locale.ru: 'чат_бот'
            }
        ),
    )
    async def chat_bot(self, inter):
        pass

    @chat_bot.sub_command(
        name=Localized(
            'clear_chat',
            data={
                Locale.ru: 'отчистить_чат'
            }
        ),
        description=Localized(
            'delete your chat with the bot',
            data={
                Locale.ru: 'удалите ваш чат с ботом',
            }
        ),
    )
    async def chat_bot_clear(
            self,
            inter
    ):
        async def handler():
            if inter.user.id in self.chats:
                del self.chats[inter.user.id]
                
            await inter.send(
                embed=disnake.Embed(
                    title='чат бот' if inter.locale == Locale.ru else 'chat bot',
                    description='чат отчищен' if inter.locale == disnake.Locale.ru else 'the chat has been cleared',
                    color=disnake.Color.green()
                ),
                ephemeral=True
            )

        await asyncio.create_task(handler())        
    
    @commands.Cog.listener()
    async def on_button_click(self, inter):
        if inter.message.author != self.bot.user:
            return
        
        locale = inter.locale

        if inter.data.custom_id.startswith('chatbot'):
            user_id = int(inter.data.custom_id.split('_')[2])
            if user_id in self.chats:
                if inter.user.id == user_id:
                    if inter.data.custom_id.startswith('chatbot_websearch'):
                        
                        self.chats[user_id]['web_search'] = not self.chats[user_id]['web_search']

                        await inter.message.edit(components=await self.components(user_id))

                        await inter.send(
                            'поиск в гугле' if locale == Locale.ru else 'google search',
                            ephemeral=True
                        )

                    elif inter.data.custom_id.startswith('chatbot_r1'):
                        self.chats[user_id]['r1'] = not self.chats[user_id]['r1']

                        await inter.message.edit(components=await self.components(user_id))

                        await inter.send(
                            'DeepThink (R1)',
                            ephemeral=True
                        )
                    elif inter.data.custom_id.startswith('chatbot_stop'):
                        if self.chats[user_id]['content'] or self.chats[user_id]['in_progress']:
                            self.chats[user_id]['stop'] = True

                            if self.chats[user_id]['content']:
                                self.chats[user_id]['content'] += '... `system:` user stopped generation'

                            await inter.send(
                                'генерация остановлена' if locale == Locale.ru else 'generation stopped',
                                ephemeral=True
                            )
                        else:
                            await inter.send(
                                'нет процесса генерации' if locale == Locale.ru else 'there is no generation process',
                                ephemeral=True
                            )
                else:
                    await inter.send(
                        'ты не можешь изменять чужие параметры' if locale == Locale.ru else 'you cannot change other users parameters',
                        ephemeral=True
                    )
                
            else:
                await inter.send(
                    'не найден чат' if locale == Locale.ru else 'chat not found',
                    ephemeral=True
                )

def setup(bot):
    bot.add_cog(ChatBot(bot))
