#!/usr/bin/python3
import os
import discord
import asyncio
import aiohttp
import logging
import config


class Beatbot(discord.Client):
    """
    This is a Discord gateway for Beatbot.
    """

    def __init__(self):
        """
        Constructor for Beatbot
        """

        self.client_list = {}

        logging.basicConfig(filename=os.path.join(config.LOG_DIR,
                                                  'beatbot_discord.log'),
                            level=logging.INFO,
                            format='%(asctime)s - %(message)s')

        discord.Client.__init__(self)

        self.bg_task = self.loop.create_task(self._status_updater())

    async def on_ready(self):
        """
        Log to file on successful connection
        """

        Beatbot.log_to_file('Logged on as {0}!'.format(self.user))

    async def _status_updater(self):
        """
        A background task that will update the "Playing" field in Discord
        """

        await self.wait_until_ready()
        old_np_str = ''

        while not self.is_closed():
            current_song = await Beatbot.get_current_song()
            np_str = '{} - {}'.format(current_song['title'],
                                      current_song['artist'])

            if np_str != old_np_str:
                await self.change_presence(activity=discord.Game(np_str))
                old_np_str = np_str

            await asyncio.sleep(10)

    async def on_message(self, message):
        """
        Parse each incoming message and act on it if necessary.

        Parameters:
            message (discord.Message): The message
        """

        if (message.author == self.user or
                not (message.content.lower().startswith('bb ') or
                message.content.lower().startswith('beatbot '))):
            return

        args = message.content.split()

        if len(args) < 2:
            return

        command = args[1].lower()
        route = {'start': self._start_stream,
                 'play': self._start_stream,
                 'stop': self._stop_stream,
                 'end': self._stop_stream,
                 'status': self._send_status,
                 'np': self._send_status,
                 'now_playing': self._send_status,
                 'nowplaying': self._send_status,
                 'search': self._search_for_songs,
                 'find': self._search_for_songs,
                 'queue': self._queue_request,
                 'request': self._queue_request,
                 'help': self._show_help,
                 'king': self._easter_egg,
                 'gun': self._easter_egg}

        if command in route:
            await route[command](message)

    async def _show_help(self, message):
        """
        Display a help message

        Parameters:
            message (Discord.Message): The message which requested help
        """
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

        await message.channel.send(embed=Beatbot.make_embed(title='Usage:',
                                                            description=usage))

    async def _start_stream(self, message):
        """
        Determine if the stream can be started and then do so if able

        Parameters:
            message (Discord.Message): The message which issued the start
                                       command
        """

        if message.author.voice is None:
            return

        voice_channel = message.author.voice.channel

        if (voice_channel is None or self.user in voice_channel.members or
                voice_channel.guild.id in self.client_list):
            return

        voice_client = await voice_channel.connect()
        voice_client.play(discord.FFmpegPCMAudio(config.STREAM_URL,
                options='-muxdelay 0.1'))
        self.client_list[voice_channel.guild.id] = voice_client
        Beatbot.log_to_file('Stream started on {} on {}.'.format(
            voice_channel.name, voice_channel.guild.name))

    async def _stop_stream(self, message):
        """
        Determine if a stream is playing and if so, stop it

        Parameters:
            message (Discord.Message): The message which issued the stop
                                       command
        """

        if message.author.voice is None:
            return

        voice_channel = message.author.voice.channel

        if (voice_channel is None or self.user not in voice_channel.members
                or voice_channel.guild.id not in self.client_list):
            return

        await self._close_voice_client(voice_channel)

    async def on_voice_state_update(self, member, before, after):
        """
        Monitor state updates and act on them if needed

        If the bot is the last user left in its voice channel, then we no
        longer have any listeners and may as well stop the stream and leave
        the channel, as if ordered to do so

        Parameters:
            member (Discord.Member): User who changed voice state
            before (Discord.VoiceState): State before the change
            after (Discord.VoiceState): State after the change
        """

        if (before.channel is None or
                self.user not in before.channel.members or
                before.channel == after.channel or
                before.channel.guild.id not in self.client_list):
            return

        voice_client = self.client_list[before.channel.guild.id]

        if (len(voice_client.channel.members) != 1 or
                self.user not in voice_client.channel.members):
            return

        await self._close_voice_client(before.channel)

    async def _close_voice_client(self, channel):
        """
        Helper function to stop the stream and leave the channel

        Parameters:
            channel (Discord.VoiceChannel): Channel to leave
        """

        self.client_list[channel.guild.id].stop()
        await self.client_list[channel.guild.id].disconnect()
        del self.client_list[channel.guild.id]
        Beatbot.log_to_file('Stream stopped on {} on {}.'.format(
            channel.name, channel.guild.name))

    async def _send_status(self, message):
        """
        Show the currently playing song

        Parameters:
            message (Discord.Message): The request for current status
        """

        current_song = await Beatbot.get_current_song()
        reply = Beatbot.make_embed(title=current_song['title'],
                                   description="{}\n***{}***".format(
                                        current_song['artist'],
                                        current_song['album']))
        reply.set_thumbnail(url=config.IMAGE_URL + str(current_song['id']))
        await message.channel.send(embed=reply)

    async def _search_for_songs(self, message):
        """
        Search for songs to potentially queue

        Parameters:
            message (Discord.Message): The query to match against the song list
        """

        args = message.content.split()

        if len(args) < 3:
            return

        query = ' '.join(args[2:])

        async with aiohttp.ClientSession() as session:
            response = await session.get('{}search/{}'.format(
                config.SITE_URL, query))
            results = (await response.json())['results']
            description = ''

            if len(results) == 0:
                title = 'No Results Found'
            else:
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

            await message.channel.send(embed=Beatbot.make_embed(title=title,
                                       description=description))

    async def _queue_request(self, message):
        """
        Queue a request with Beatbot

        After determining that the song id is actually a digit, attempt to
        request it from Beatbot, and check the queue receipt to confirm that
        it did actually queue

        Parameters:
            message (Discord.Message): The message with the song request
        """

        args = message.content.split()

        if len(args) < 3:
            await self._easter_egg(message)
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

            await message.channel.send(embed=Beatbot.make_embed(title=title,
                                       description=description))

    async def _easter_egg(self, message):
        """
        Link a funny video in chat in response to a number of keywords

        Parameters:
            message (Discord.Message): The message which qualified for an egg
        """

        egg = message.content.split()[1].lower()

        urls = {'king': 'https://www.youtube.com/watch?v=9P-DFZ3HOPQ',
                'gun': 'https://www.youtube.com/watch?v=-LgEvQuyDxE',
                'queue': 'https://www.youtube.com/watch?v=WPkMUU9tUqk'}

        if egg in urls:
            await message.channel.send(urls[egg])

    async def get_current_song():
        """
        Get the current song from beatbot and return it.
        """
        async with aiohttp.ClientSession() as session:
            response = await session.get('{}now_playing'.format(
                config.SITE_URL))

            now_playing = await response.json()
            return now_playing['currentsong']

    def make_embed(color=config.EMBED_COLOR,
                   url=config.SITE_URL,
                   title='',
                   description=''):
        """
        Create an embed using the parameters provided.

        Parameters:
            color (Union[Discord.Colour, int]): The color of the embed
            url (str): The url to link to in the title of the embed
            title (str): The text to use for the title of the embed
            description (str): The main body of the embed

        Returns:
            Discord.Embed: An embed that can be edited or sent on immediately
        """

        embed = discord.Embed(color=color,
                              url=url,
                              title=title,
                              description=description)
        embed.set_footer(text=config.FOOTER_URL)
        return embed

    def log_to_file(message):
        """
        Helper log function

        Parameters:
            message (str): What to log to file
        """

        logging.info(str(message))

discord.opus.load_opus('libopus.so')
beatbot = Beatbot()
beatbot.run(config.LOGIN_TOKEN)
