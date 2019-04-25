import discord
import config

class Beatbot(discord.Client):
    def __init__(self):
        self.__streaming = False
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

        if command == 'start':
            await self.__start_stream(message)
        elif command == 'stop':
            await self.__stop_stream()

    async def __start_stream(self, message):
        if not self.__streaming:
            # get channel of caller
            channel = message.author.voice.channel

            if channel is None:
                return

            # join channel
            self.__voice_client = await channel.connect()

            # start streaming
            self.__stream = discord.FFmpegPCMAudio(config.STREAM_URL)
            self.__voice_client.play(self.__stream)

            print('Stream started')
            self.__streaming = True

    async def __stop_stream(self):
        if self.__streaming:
            if self.__voice_client is not None:
                # stop streaming
                self.__voice_client.stop()
                self.__stream.cleanup()

                # leave channel
                await self.__voice_client.disconnect()

            print('Stream stopped')
            self.__streaming = False

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
