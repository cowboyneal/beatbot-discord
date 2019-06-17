#!/usr/bin/python3
import os
import discord
import asyncio
import aiohttp
import logging
import config

from musicpd import MPDClient


class Beatbot(discord.Client):

    def __init__(self):
        self.client_list = {}
        self.mpd = MPDClient()
        self.mpd.connect(config.MPD_ADDRESS, config.MPD_PORT)

        logging.basicConfig(filename=os.path.join(config.LOG_DIR,
                                                  'beatbot_discord.log'),
                                                  level=logging.INFO,
                            format='%(asctime)s - %(message)s')

        discord.Client.__init__(self)

        self.bg_task = self.loop.create_task(self.__status_updater())

    async def on_ready(self):
        Beatbot.log_to_file('Logged on as {0}!'.format(self.user))

    async def __status_updater(self):
        await self.wait_until_ready()
        old_np_str = ''

        while not self.is_closed():
            current_song = self.mpd.currentsong()
            np_str = '{} - {}'.format(current_song['title'],
                                      current_song['artist'])

            if np_str != old_np_str:
                await self.change_presence(activity=discord.Game(np_str))
                old_np_str = np_str

            await asyncio.sleep(10)

    async def on_message(self, message):
        if message.author == self.user:
            return

        if (message.content.lower().startswith('bb ') or
                message.content.lower().startswith('beatbot ')):
            await self.__parse_command(message)

    async def __parse_command(self, message):
        args = message.content.split()

        if len(args) < 2:
            return

        command = args[1].lower()

        if command == 'start' or command == 'play':
            await self.__start_stream(message)
        elif command == 'stop' or command == 'end':
            await self.__stop_stream(message)
        elif (command == 'status' or command == 'np' or
                command == 'nowplaying' or command == 'now_playing'):
            await self.__send_status(message)
        elif command == 'search' or command == 'find':
            await self.__search_for_songs(message)
        elif command == 'queue' or command == 'request':
            await self.__queue_request(message)
        elif command == 'king' or command == 'gun':
            await self.__easter_egg(message)
        elif command == 'help':
            await self.__show_help(message)

    async def __show_help(self, message):
        usage = ("**help**: This message\n"
                 '**start** | **play**: Join your voice channel and start '
                        "streaming\n"
                 '**stop** | **end**: Stop streaming and leave voice '
                        "channel\n"
                 '**status** | **now_playing** | **nowplaying** | **np**: '
                        "Show current playing song\n"
                 '**search** | **find** <**query**>: Search for a song to '
                        "request\n"
                 '**queue** | **request** <**id**>: Queue a song')

        reply = discord.Embed(color=config.EMBED_COLOR,
                              url=config.SITE_URL,
                              title='Usage:',
                              description=usage)
        reply.set_footer(text=config.FOOTER_URL)

        await message.channel.send(embed=reply)

    async def __start_stream(self, message):
        # get channel of caller
        if not hasattr(message.author, 'voice'):
            return

        voice_channel = message.author.voice.channel

        if (voice_channel is None or self.user in voice_channel.members or
                voice_channel.guild.id in self.client_list):
            return

        # join channel
        voice_client = await voice_channel.connect()

        # start streaming
        voice_client.play(discord.FFmpegPCMAudio(config.STREAM_URL))

        self.client_list[voice_channel.guild.id] = voice_client
        Beatbot.log_to_file('Stream started on {} on {}.'.format(
            voice_channel.name, voice_channel.guild.name))

    async def __stop_stream(self, message):
        if not hasattr(message.author, 'voice'):
            return

        voice_channel = message.author.voice.channel

        if (voice_channel is None or self.user not in voice_channel.members
                or voice_channel.guild.id not in self.client_list):
            return

        await self.__close_voice_client(voice_channel)

    async def on_voice_state_update(self, member, before, after):
        if (self.user not in before.channel.members or
                before.channel == after.channel or
                before.channel.guild.id not in self.client_list):
            return

        voice_client = self.client_list[before.channel.guild.id]

        if (len(voice_client.channel.members) != 1 or
                self.user not in voice_client.channel.members):
            return

        await self.__close_voice_client(before.channel)

    async def __close_voice_client(self, channel):
        self.client_list[channel.guild.id].stop()
        await self.client_list[channel.guild.id].disconnect()
        del self.client_list[channel.guild.id]
        Beatbot.log_to_file('Stream stopped on {} on {}.'.format(
            channel.name, channel.guild.name))

    async def __send_status(self, message):
        current_song = self.mpd.currentsong()

        reply = discord.Embed(color=config.EMBED_COLOR,
                              url=config.SITE_URL,
                              title=current_song['title'],
                              description="{}\n***{}***".format(current_song['artist'],
                                                                current_song['album']))
        reply.set_thumbnail(url=config.IMAGE_URL +
                            str(current_song['id']))
        reply.set_footer(text=config.FOOTER_URL)

        await message.channel.send(embed=reply)

    async def __search_for_songs(self, message):
        args = message.content.split()

        if len(args) < 3:
            return

        query = ' '.join(args[2:])

        async with aiohttp.ClientSession() as session:
            response = await session.get('{}search/{}'.format(
                config.SITE_URL, query))
            results = (await response.json())['results']

            if len(results) == 0:
                title = 'No Results Found'
                description = ''
            else:
                description = ''
                for song in results:
                    description += "**{}**: {} - {}\n".format(song['id'],
                                                              song['title'],
                                                              song['artist'])

                if len(description) > 2048:
                    title = 'Too Many Results'
                    description = ('Too many results to display. '
                                   'Perhaps try narrowing your search.')
                else:
                    title = 'Search Results'

            reply = discord.Embed(color=config.EMBED_COLOR,
                                  url=config.SITE_URL,
                                  title=title,
                                  description=description)
            reply.set_footer(text=config.FOOTER_URL)
            await message.channel.send(embed=reply)

    async def __queue_request(self, message):
        args = message.content.split()

        if len(args) < 3:
            await self.__easter_egg(message)
            return

        song_id = args[2]

        if song_id.isdigit():
            song_id = int(song_id)
        else:
            return

        async with aiohttp.ClientSession() as session:
            response = await session.get('{}queue_request/{}'.format(
                config.SITE_URL, str(song_id)))

            receipt = await response.json()
            description = ''

            if receipt['success']:
                title = 'Request Queued'
                description = 'Successfully queued **{}** - **{}**.'.format(
                    receipt['title'], receipt['artist'])
            else:
                title = 'Request Failed'

            reply = discord.Embed(color=config.EMBED_COLOR,
                                  url=config.SITE_URL,
                                  title=title,
                                  description=description)
            reply.set_footer(text=config.FOOTER_URL)
            await message.channel.send(embed=reply)

    async def __easter_egg(self, message):
        egg = message.content.split()[1].lower()

        if egg == 'king':
            await message.channel.send(
                'https://www.youtube.com/watch?v=9P-DFZ3HOPQ')
        elif egg == 'gun':
            await message.channel.send(
                'https://www.youtube.com/watch?v=-LgEvQuyDxE')
        elif egg == 'queue':
            await message.channel.send(
                'https://www.youtube.com/watch?v=WPkMUU9tUqk')

    def log_to_file(message):
        logging.info(str(message))

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
