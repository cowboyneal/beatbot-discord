#!/usr/bin/python3
import os
import discord
import logging
import config

class Beatbot(discord.Client):
    def __init__(self):
        self.client_list = {}
        discord.Client.__init__(self)

    async def on_ready(self):
        Beatbot.log_to_file('beatbot_discord',
                'Logged on as {0}!'.format(self.user))

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
        Beatbot.log_to_file('beatbot_discord', 'Stream started on ' +
                voice_channel.name + ' on ' + voice_channel.guild.name
                + '.')

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
        Beatbot.log_to_file('beatbot_discord', 'Stream stopped on ' +
                voice_channel.name + ' on ' + voice_channel.guild.name
                + '.')

    def log_to_file(file_name, message):
        fmt_str = '%(asctime)s - %(message)s'
        file_path = os.path.join(config.LOG_DIR, file_name + '.log')

        logging.basicConfig(filename=file_path, level=logging.INFO,
                format=fmt_str)

        logging.info(str(message))

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
