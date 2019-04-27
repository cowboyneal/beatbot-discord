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
                'beatbot_discord.log'), level=logging.INFO,
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
            np_str = current_song['title'] + ' - ' + current_song['artist']

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
        command = message.content.split()[1].lower()

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
        Beatbot.log_to_file('Stream started on ' + voice_channel.name +
                ' on ' + voice_channel.guild.name + '.')

    async def __stop_stream(self, message):
        if not hasattr(message.author, 'voice'):
            return

        voice_channel = message.author.voice.channel

        if (voice_channel is None or self.user not in voice_channel.members
                or self.client_list[voice_channel.guild.id] is None):
            return

        # stop streaming
        self.client_list[voice_channel.guild.id].stop()

        # leave channel
        await self.client_list[voice_channel.guild.id].disconnect()

        del self.client_list[voice_channel.guild.id]
        Beatbot.log_to_file('Stream stopped on ' + voice_channel.name +
                ' on ' + voice_channel.guild.name + '.')

    async def __send_status(self, message):
        current_song = self.mpd.currentsong()

        reply = discord.Embed(color=discord.Colour.dark_blue(),
                url=config.SITE_URL,
                title=current_song['title'],
                description=current_song['artist'] + "\n***" +
                    current_song['album'] + '***')
        reply.set_thumbnail(url=config.IMAGE_URL +
                str(current_song['id']))
        reply.set_footer(text=config.FOOTER_URL)

        await message.channel.send(embed=reply)

    async def __search_for_songs(self, message):
        query = ' '.join(message.content.split()[2:])

        async with aiohttp.ClientSession() as session:
            response = await session.get(config.SITE_URL + 'search/' +
                    query)
            results = (await response.json())['results']

            if len(results) == 0:
                reply = discord.Embed(color=discord.Colour.dark_blue(),
                        url=config.SITE_URL,
                        title='No Results Found')
            else:
                description = ''
                for song in results:
                    description += '**' + song['id'] + '**: ' + \
                            song['title'] + ' - ' + song['artist'] + "\n"

                reply = discord.Embed(color=discord.Colour.dark_blue(),
                        url=config.SITE_URL,
                        title='Search Results',
                        description=description)
            reply.set_footer(text=config.FOOTER_URL)
            await message.channel.send(embed=reply)

    async def __queue_request(self, message):
        song_id = int(message.content.split()[2])

        async with aiohttp.ClientSession() as session:
            response = await session.get(config.SITE_URL + 'queue_request/'
                    + song_id)

            if (await response.json())['success']:
                title = 'Request Queued'
            else:
                title = 'Request Failed'

            reply = discord.Embed(color=discord.Colour.dark_blue(),
                    url=config.SITE_URL,
                    title=title)
            reply.set_footer(text=config.FOOTER_URL)
            await message.channel.send(embed=reply)

    def log_to_file(message):
        logging.info(str(message))

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
