import discord
import config

class MyClient(discord.Client):
    async def on_ready(self):
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self, message):
        print('Message from {0.author}: {0.content}'.format(message))

        if (message.content.startswith('bb') or
                message.content.startswith('beatbot')):
            parse_command(message)

    def parse_command(message):
        command = message.content.split()[1]

        if command == 'start':
            start_stream()
        elif command == 'stop':
            stop_stream()

    def start_stream():
        print('Stream started')

    def stop_stream():
        print('Stream stopped')

client = MyClient()
client.run(config.LOGIN_TOKEN)
