#!/usr/bin/python3
import os
import discord
import asyncio
import logging
import config

from musicpd import MPDClient

class Beatbot(discord.Client):
    def __init__(self):
        self.client_list = {}
        self.mpd         = MPDClient()
        self.mpd_monitor = MPDClient()

        logging.basicConfig(filename=os.path.join(config.LOG_DIR,
                'beatbot_discord.log'), level=logging.INFO,
                format='%(asctime)s - %(message)s')

        discord.Client.__init__(self)

        self.bg_task = self.loop.create_task(self.__status_updater())

    async def on_ready(self):
        Beatbot.log_to_file('Logged on as {0}!'.format(self.user))

    async def __status_updater(self):
        await self.wait_until_ready()
        old_np = None
        self.mpd_monitor.connect(config.MPD_ADDRESS, config.MPD_PORT)

        while not self.is_closed():
            current_song = self.mpd_monitor.currentsong()
            now_playing = discord.Game(current_song['title'] + ' - ' +
                    current_song['artist'])

            if now_playing != old_np:
                await self.change_presence(activity=now_playing)
                old_np = now_playing

            await asyncio.sleep(5)

    async def on_message(self, message):
        if message.author == self.user:
            return

        if (message.content.startswith('bb') or
                message.content.startswith('beatbot')):
            await self.__parse_command(message)

    async def __parse_command(self, message):
        command = message.content.split()[1]

        if command == 'start' or command == 'play':
            await self.__start_stream(message)
        elif command == 'stop' or command == 'end':
            await self.__stop_stream(message)
        elif command == 'status' or command == 'np':
            await self.__send_status(message)

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
        self.mpd.connect(config.MPD_ADDRESS, config.MPD_PORT)

        current_song = self.mpd.currentsong()

        self.mpd.close()
        self.mpd.disconnect()

        response = discord.Embed(color=discord.Colour.dark_blue(),
                title=current_song['title'],
                description=current_song['artist'])
        thumbnail = config.IMAGE_URL + str(current_song['id'])
        response.set_thumbnail(url=thumbnail)

        await message.channel.send(embed=response)

    def log_to_file(message):
        logging.info(str(message))

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
