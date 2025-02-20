import disnake
from disnake.ext import commands
import os
import random
import asyncio
from utils import web_search, config
import aiohttp
import json
from langdetect import detect
from disnake import Locale, Localized


class ChatBotSystem:
    def __init__(self, user_id):
        self.token_limit = 500
        self.user_id = user_id

        self.models = {
            'deepseek': {
                'model': 'deepseek/deepseek-chat',
                'reasoning': 'deepseek/deepseek-r1:free',
                'func': self.openrouter_generating_2,
                'key': os.environ['OPENROUTER']
            },
            'qwen': {
                'model': 'qwen/qwen-vl-plus:free',
                'reasoning': False,
                'func': self.openrouter_generating,
                'key': os.environ['OPENROUTER']
            }
        }
        self.current_model = random.choice([model for model, _ in self.models.items()])

        self.messages = []
        self.internet_search = False
        self.google_search = False
        self.reasoning = False
        self.lange = None

        self.process = False
        self.stop_command = False

        self.results = {
            'content': '',
            'reasoning': '',
            'embeds': [],
            'model': self.current_model,
        }

    def clear_results(self):
        self.results = {
            'content': '',
            'reasoning': '',
            'embeds': [],
            'model': self.current_model,
        }

    def get_results(self):
        return self.results

    async def generate(self, content, regenerate=False):
        self.process = True

        if regenerate:
            self.messages.pop(-1)
            if self.messages[-1]['role'] == 'system':
                self.messages.pop(-1)

        if not self.lange and content:
            try:
                lange = detect(content)
                self.lange = lange if lange in ['ru', 'en'] else 'ru'
            except:
                self.lange = random.choice(['ru', 'en'])
        
        asyncio.create_task(self.models[self.current_model]['func'](content))
        return self.process

    def change_model(self, model):
        if model in self.models:
            self.current_model = model

    def stop(self):
        self.stop_command = True

    def change_reasoning(self):
        if not self.reasoning:
            if self.models[self.current_model]['reasoning']:
                self.reasoning = True

                return True
            else:
                return False
        else:
            self.reasoning = False
            return True
        
    def enable_internet_search(self, google_search=False, internet_search=False):
        if internet_search:
            self.internet_search = not self.internet_search
            if google_search:
                self.google_search = False
        elif google_search:
            self.google_search = not self.google_search
            if internet_search:
                self.internet_search = False

    def get_components(self):
        models_list = []
        for key, _ in self.models.items():
            models_list.append(disnake.SelectOption(label=key, value=key)),
        
        if not self.process:
            cmp_list = [
                disnake.ui.Button(
                    emoji='<:google:1339203500558520351>',
                    style=disnake.ButtonStyle.blurple if self.google_search else disnake.ButtonStyle.grey,
                    custom_id=f'chatbot_google_{self.user_id}'
                ),
                disnake.ui.Button(
                    emoji='<:search:1339218256866840586>',
                    style=disnake.ButtonStyle.blurple if self.internet_search else disnake.ButtonStyle.grey,
                    custom_id=f'chatbot_websearch_{self.user_id}'
                ),
                disnake.ui.Button(
                    emoji='🧠',
                    style=disnake.ButtonStyle.blurple if self.reasoning else disnake.ButtonStyle.grey,
                    custom_id=f'chatbot_reasoning_{self.user_id}'
                ),
                disnake.ui.Button(
                    emoji='<:restart:1339218430523609128>',
                    style=disnake.ButtonStyle.gray,
                    custom_id=f'chatbot_regenerate_{self.user_id}'
                ),
                disnake.ui.Button(
                    label='отчистить чат' if self.lange == 'ru' else 'clear chat',
                    style=disnake.ButtonStyle.red,
                    custom_id=f'chatbot_clear_{self.user_id}'
                ),
                disnake.ui.Select(
                    placeholder=self.current_model,
                    options=models_list,
                    custom_id=f'chatbot_model_{self.user_id}'
                ),
            ]
        else:
            cmp_list = [
                disnake.ui.Button(
                    emoji='⬜',
                    style=disnake.ButtonStyle.red,
                    custom_id=f'chatbot_stop_{self.user_id}'
                ),
                disnake.ui.Button(
                    label='проверить' if self.lange == 'ru' else 'check',
                    style=disnake.ButtonStyle.success,
                    custom_id=f'chatbot_check_{self.user_id}'
                )
            ]
        
        return cmp_list

    async def web_search(self, content):
        if self.internet_search or self.google_search:
            icon = 'https://lh3.googleusercontent.com/COxitqgJr1sJnIDe8-jiKhxDx1FrYbtRHKJ9z_hELisAlapwE9LUPh6fcXIfb5vwpbMl4xl9H9TRFPc5NOO8Sb3VSgIBrfRYvW6cUA'
            if self.internet_search:
                result = web_search.lange_search(content)
                icon = 'https://cdn-icons-png.flaticon.com/512/1011/1011322.png'
            elif self.google_search:
                self.google_search = not self.google_search
                result = web_search.google_search(content)

            self.messages.append({"role": "user", "system": "web search results (the user has enabled web search):\n" + str(result)})
            self.results['embeds'].append(
                disnake.Embed(
                    title='веб поиск' if self.lange == 'ru' else 'web search',
                    description=str(result)[:1997] + '...' if len(result) > 2000 else str(result)
                ).set_thumbnail(icon)
            )

    async def openrouter_generating(self, content):
        if content:
            self.messages.append({"role": "user", "content": content})
            
        await self.web_search(content)

        model = self.models[self.current_model]['reasoning'] if (self.reasoning and self.models[self.current_model]['reasoning']) else self.models[self.current_model]['model']
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.models[self.current_model]['key']}",
            "Content-Type": "application/json"
        }
        data=json.dumps({
            "model": model,
            "messages": self.messages,
            "include_reasoning": self.reasoning,
            "max_tokens": self.token_limit,
            "stream": True, 
        })
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    async for line in response.content:
                        if self.stop_command:
                            self.stop_command = False
                            break

                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line.startswith('data:'):
                            try:
                                json_data = json.loads(decoded_line[5:])
                                if 'error' in json_data:
                                    self.results['content'] = 'error: ' + json_data['error']['message']
                                    break

                                content = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                reasoning = json_data.get("choices", [{}])[0].get("delta", {}).get("reasoning", "")

                                if content:
                                    self.results['content'] += content
                                if reasoning:
                                    self.results['reasoning'] += reasoning
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            self.results['content'] = f"error: {e}"

        self.messages.append(
            {
                "role": "assistant", "content": (self.results['content'] + 'system: your reasoning:\n' + str(self.results['reasoning']) if self.results['reasoning'] else self.results['content'])
            }
        )
        self.process = False

    async def openrouter_generating_2(self, content):
        if content:
            self.messages.append({"role": "user", "content": content})
            
        await self.web_search(content)

        model = self.models[self.current_model]['reasoning'] if (self.reasoning and self.models[self.current_model]['reasoning']) else self.models[self.current_model]['model']
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.models[self.current_model]['key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": self.messages,
            "include_reasoning": self.reasoning,
            "max_tokens": self.token_limit,
            "stream": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    async for line in response.content:
                        if self.stop_command:
                            self.stop_command = False
                            break

                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line.startswith('data:'):
                            try:
                                json_data = json.loads(decoded_line[5:])
                                if 'error' in json_data:
                                    self.results['content'] = 'error: ' + json_data['error']['message']
                                    break

                                content = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                reasoning = json_data.get("choices", [{}])[0].get("delta", {}).get("reasoning", "")

                                if content:
                                    self.results['content'] += content
                                if reasoning:
                                    self.results['reasoning'] += reasoning
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            self.results['content'] = f"error: {e}"

        self.messages.append(
            {
                "role": "assistant", "content": (self.results['content'] + 'system: your reasoning:\n' + str(self.results['reasoning']) if self.results['reasoning'] else self.results['content'])
            }
        )
        self.process = False


class ChatBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chats = {}

    async def check(self, message) -> bool:
        # ну тут короче сами делайте что нужно
        if not message.guild:
            return True
            
        if not content.replace(" ", "").replace(self.bot.user.mention, ""):
            return False
        
        if message.mentions and len(message.mentions) > 2:
            return False
        if not message.channel.is_nsfw():
            return True
            
        return False
        
    async def main(self, chat, message, user_id, content=True):
        while chat.process:
            await asyncio.sleep(1)

        chat.process = True

        asyncio.create_task(chat.generate(
                message.content.replace(self.bot.user.mention, '') if content else False
            )
        )

        bot_message = await message.channel.send('...', reference=message)

        while chat.process:
            await asyncio.sleep(1)
            await self.message(bot_message, user_id)

        await self.message(bot_message, user_id)

        chat.clear_results()
        print(self.chats[user_id].messages)
        return True

    async def message(self, message, user_id):
        results = self.chats[user_id].get_results()

        message_content = results['content']
        reasoning_embed = disnake.Embed(
            title='размышления' if self.chats[user_id].get_lange() == 'ru' else 'reasoning',
            description=results['reasoning']
        ) if results['reasoning'] else None
        embeds = []
        if results['embeds']:
            embeds.append(
                results['embeds']
            )
        if reasoning_embed:
            embeds.insert(0, reasoning_embed)

        await message.edit(
            content=message_content,
            embeds=embeds,
            components=self.chats[user_id].get_components()
        )

    async def on_message(self, message):
        user_id = message.author.id

        if (not message.guild or self.bot.user.mentioned_in(message)) and await self.check(message):
            chat = self.chats.setdefault(user_id, ChatBotSystem(user_id))

            result = await self.main(chat, message, user_id)
            return result

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
            'manage',
            data={
                Locale.ru: 'управлять'
            }
        ),
        description=Localized(
            'manage a chat with a bot (emergency actions)',
            data={
                Locale.ru: 'управлять чатом с ботом (экстренные действия)',
            }
        ),
    )
    async def chat_bot_manage(
        self,
        inter,
        action: bool = commands.Param(
            name=Localized('action', data={Locale.ru: 'действие'}),
            choices=[
                disnake.OptionChoice(Localized('stop', data={Locale.ru: 'остановить'}), 'stop'),
                disnake.OptionChoice(Localized('delete_chat', data={Locale.ru: 'удалить_чат'}), 'delete_chat'),
                disnake.OptionChoice(Localized('check', data={Locale.ru: 'проверить'}), 'check'),
            ],
            default=False
        ),
    ):
        chat = self.chats.setdefault(inter.author.id, ChatBotSystem(inter.author.id))

        locale = inter.locale
        ru = Locale.ru

        if action == 'stop':
            chat.stop()
            await inter.send('остановлено' if inter.locale == Locale.ru else 'stopped', ephemeral=True)
        elif action == 'delete_chat':
            del self.chats[inter.author.id]
            await inter.send('чат удален' if inter.locale == Locale.ru else 'chat deleted', ephemeral=True)
        elif action == 'check':
            status = chat.check_process()
            await inter.send(
                ('✅ процесс активен' if status else '❌ процесс не активен') if locale == ru else ('✅ process active' if status else '❌ process not active'),
                ephemeral=True
            )

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @chat_bot.sub_command(
        name=Localized(
            'config',
            data={
                Locale.ru: 'конфиг'
            }
        ),
        description=Localized(
            'chat bot config',
            data={
                Locale.ru: 'конфиг чат бота',
            }
        ),
    )
    async def chat_bot_config(
        self,
        inter
    ):
        locale = inter.locale

        embed, components = self.config_components(inter, locale)

        await inter.send(
            embed=embed,
            components=components
        )

    @commands.Cog.listener()
    async def on_button_click(self, inter):
        if inter.message.author != self.bot.user:
            return

        locale = inter.locale
        ru = Locale.ru
        inter_user_id = inter.author.id
        custom_id = inter.data.custom_id

        elif custom_id.startswith('chatbot'):
            user_id = int(custom_id.split('_')[2])

            if user_id != inter_user_id:
                await inter.send(
                    'это не твои параметры' if locale == ru else 'this is not your parameters',
                    ephemeral=True
                )
                return
            if user_id not in self.chats:
                await inter.send(
                    'чат не найден' if locale == ru else 'chat not found',
                    ephemeral=True
                )
                return

            chat = self.chats.setdefault(user_id, ChatBotSystem(user_id))      

            if custom_id.startswith('chatbot_stop'):
                chat.stop()
                await inter.send(
                    'остановлено' if locale == ru else 'stopped',
                    ephemeral=True
                )
            elif custom_id.startswith('chatbot_check'):
                status = chat.process
                await inter.send(
                    ('✅ процесс активен' if status else '❌ процесс не активен') if locale == ru else ('✅ process active' if status else '❌ process not active'),
                    ephemeral=True
                )
            # пошло все что не для активного процесса
            elif custom_id.startswith('chatbot_google'):
                chat.enable_internet_search(google_search=True)
                await inter.message.edit(
                    components=chat.get_components()
                )
                await inter.send('поиск в гугле' if locale == ru else 'google search', ephemeral=True)
            elif custom_id.startswith('chatbot_websearch'):
                chat.enable_internet_search(internet_search=True)
                await inter.message.edit(
                    components=chat.get_components()
                )
                await inter.send('поиск в интернете' if locale == ru else 'internet search', ephemeral=True)
            elif custom_id.startswith('chatbot_reasoning'):
                result = chat.change_reasoning()
                if result:
                    await inter.message.edit(
                        components=chat.get_components()
                    )
                    await inter.send('размышления' if locale == ru else 'reasoning', ephemeral=True)
                else:
                    await inter.send(
                        'модель не потдерживает размышления' if locale == ru else 'model does not support reasoning',
                        ephemeral=True
                    )
            # проверка т.к. остальное не работает если активен процесс
            if chat.process:
                await inter.send(
                    'процесс активен, действие невозможно'if locale == ru else 'process active, action is impossible',
                    ephemeral=True
                )
                return
            
            if custom_id.startswith('chatbot_regenerate'):
                if not chat.messages:
                    await inter.send(
                        'в чате нету сообщений' if locale == ru else 'no messages in the chat',
                        ephemeral=True
                    )
                    return
                
                await inter.send(
                    'запуcкаю...' if locale == ru else 'starting...',
                    ephemeral=True
                )
                await chat.generate(
                    False,
                    regenerate=True
                )
                await self.main(chat, inter.message, user_id, False)
            elif custom_id.startswith('chatbot_clear'):
                del self.chats[user_id]
                await inter.send(
                    'чат удален (кнопки теперь не работают если что)' if locale == ru else 'chat deleted (the buttons dont work anymore if anything)',
                    ephemeral=True
                )
                
    @commands.Cog.listener()
    async def on_dropdown(self, inter):
        if inter.message.author != self.bot.user:
            return
        
        locale = inter.locale
        ru = Locale.ru
        inter_user_id = inter.author.id
        custom_id = inter.data.custom_id

        if custom_id.startswith('chatbot'):
            user_id = int(custom_id.split('_')[2])

            if user_id != inter_user_id:
                await inter.send(
                    'это не твои параметры' if locale == ru else 'this is not your parameters',
                    ephemeral=True
                )
                return

            chat = self.chats.setdefault(user_id, ChatBotSystem(user_id))

            if inter.data.custom_id.startswith('chatbot_model'):
                model = inter.data.values[0]
                chat.change_model(model)
                await inter.message.edit(
                    components=chat.get_components()
                )
                await inter.send(
                    f'модель изменена - `{model}`' if locale == ru else f'model changed - `{model}`',
                    ephemeral=True
                )
            

def setup(bot):
    bot.add_cog(ChatBot(bot))   
