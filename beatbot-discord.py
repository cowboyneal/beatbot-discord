import discord
import config

class Beatbot(discord.Client):
    def __init__(self):
        self.client_list = {}
        discord.Client.__init__(self)

    async def on_ready(self):
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self, message):
        if message.author == self.user:
            return

        print('Message from {0.author}: {0.content}'.format(message))

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

        if voice_channel is None:
            return

        if self.user in voice_channel.members:
            return

        # join channel
        voice_client = await voice_channel.connect()

        # start streaming
        stream = discord.FFmpegPCMAudio(config.STREAM_URL)
        voice_client.play(stream)

        self.client_list[voice_channel.id] = voice_client

        print('Stream started')

    async def __stop_stream(self, message):
        voice_channel = message.author.voice.channel

        if voice_channel is None:
            return

        if self.user not in voice_channel.members:
            return

        if self.client_list[voice_channel.id] is not None:
            # stop streaming
            self.client_list[voice_channel.id].stop()

            # leave channel
            await self.client_list[voice_channel.id].disconnect()
            del self.client_list[voice_channel.id]

            print('Stream stopped')

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
