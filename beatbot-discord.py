#!/usr/bin/python3
import os
import sys
import discord
from discord import app_commands
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

        intents = discord.Intents.default()
        intents.message_content = True
        discord.Client.__init__(self, intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.bg_task = self.loop.create_task(self._status_updater())

    async def on_ready(self):
        """
        Log to file on successful connection
        """

        Beatbot.log_to_file('Logged on as {0}!'.format(self.user))

    async def on_resumed(self):
        """
        Restart status updater task
        """

        self.bg_task.cancel()
        await self.bg_task
        self.bg_task = self.loop.create_task(self._status_updater())

    async def _status_updater(self):
        """
        A background task that will update the "Playing" field in Discord
        """

        try:
            while True:
                await self.wait_until_ready()
                old_np_str = ''
                Beatbot.log_to_file('Status Updater started')

                while not self.is_closed():
                    try:
                        current_song = await Beatbot.get_current_song()
                        np_str = '{} - {}'.format(current_song['title'],
                                                  current_song['artist'])

                        if np_str != old_np_str:
                            await self.change_presence(
                                    activity=discord.Game(np_str))
                            old_np_str = np_str
                    except:
                        error = sys.exc_info()
                        Beatbot.log_to_file('EXCEPTION CAUGHT: '
                                + str(error[0]))
                        Beatbot.log_to_file('VALUE: ' + str(error[1]))
                        Beatbot.log_to_file('TRACEBACK: ' + str(error[2]))

                    await asyncio.sleep(15)

                Beatbot.log_to_file('Status Updater stopped')
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            Beatbot.log_to_file('Status Updater stopped')

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
        route = {'start':       self._start_stream_onmsg,
                 'play':        self._start_stream_onmsg,
                 'stop':        self._stop_stream_onmsg,
                 'end':         self._stop_stream_onmsg,
                 'status':      self._send_status_onmsg,
                 'np':          self._send_status_onmsg,
                 'now_playing': self._send_status_onmsg,
                 'nowplaying':  self._send_status_onmsg,
                 'search':      self._search_for_songs_onmsg,
                 'find':        self._search_for_songs_onmsg,
                 'queue':       self._queue_request_onmsg,
                 'request':     self._queue_request_onmsg,
                 'help':        self._show_help,
                 'sync_tree':   self._sync_tree,
                 'king':        self._easter_egg,
                 'gun':         self._easter_egg,
                 'ldrizzy':     self._easter_egg}

        if command in route:
            await route[command](message)

    async def _sync_tree(self, message):
        if (str(message.author) == config.ADMIN_NAME):
            await self.tree.sync()
            Beatbot.log_to_file('Application commands synced')
            await message.channel.send('Application commands have been synced.')

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
                 '(**search** | **find**) <**query**>: Search for a song to '
                        "request\n"
                 '(**queue** | **request**) <**id**>: Queue a song')

        await message.channel.send(embed=Beatbot.make_embed(title='Usage:',
                                                            description=usage))

    async def _start_stream_onmsg(self, message):
        """
        Determine if the stream can be started and then do so if able

        Parameters:
            message (Discord.Message): The message which issued the start
                                       command
        """

        await self.start_stream(message.author)

    async def start_stream(self, member):
        if member.voice is None:
            return 'Could not find voice channel.'

        voice_channel = member.voice.channel

        if (voice_channel is None or self.user in voice_channel.members or
                voice_channel.guild.id in self.client_list):
            return 'Could not join voice channel.'

        voice_client = await voice_channel.connect()
        voice_client.play(discord.FFmpegPCMAudio(config.STREAM_URL,
                options='-muxdelay 0.1'))
        self.client_list[voice_channel.guild.id] = voice_client
        Beatbot.log_to_file('Stream started in {} on {}.'.format(
            voice_channel.name, voice_channel.guild.name))
        return 'Stream started in {}.'.format(voice_channel.name)

    async def _stop_stream_onmsg(self, message):
        """
        Determine if a stream is playing and if so, stop it

        Parameters:
            message (Discord.Message): The message which issued the stop
                                       command
        """

        await self.stop_stream(message.author)

    async def stop_stream(self, member):
        if member.voice is None:
            return 'You are not in a voice channel.'

        voice_channel = member.voice.channel

        if (voice_channel is None or self.user not in voice_channel.members
                or voice_channel.guild.id not in self.client_list):
            return 'Bot is not in voice channel for this guild.'

        await self._close_voice_client(voice_channel)
        return 'Stream stopped in {}.'.format(voice_channel.name)

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

    async def get_status_embed():
        current_song = await Beatbot.get_current_song()
        reply = Beatbot.make_embed(title=current_song['title'],
                                   description="{}\n***{}***".format(
                                        current_song['artist'],
                                        current_song['album']))
        reply.set_thumbnail(url=config.IMAGE_URL + str(current_song['id']))
        return reply

    async def _send_status_onmsg(self, message):
        """
        Show the currently playing song

        Parameters:
            message (Discord.Message): The request for current status
        """

        reply = await Beatbot.get_status_embed()
        await message.channel.send(embed=reply)

    async def _search_for_songs_onmsg(self, message):
        """
        Search for songs to potentially queue

        Parameters:
            message (Discord.Message): The query to match against the song list
        """

        args = message.content.split()

        if len(args) < 3:
            return

        query = ' '.join(args[2:])
        reply = await Beatbot.search_for_songs(query)
        await message.channel.send(embed=reply)

    async def search_for_songs(query):
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

            return Beatbot.make_embed(title=title, description=description)

    async def _queue_request_onmsg(self, message):
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

        reply = await Beatbot.queue_request(song_id)
        await message.channel.send(embed=reply)

    async def queue_request(song_id):
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

            return Beatbot.make_embed(title=title, description=description)

    async def _easter_egg(self, message):
        """
        Link a funny video in chat in response to a number of keywords

        Parameters:
            message (Discord.Message): The message which qualified for an egg
        """

        egg = message.content.split()[1].lower()

        urls = {'king': 'https://www.youtube.com/watch?v=9P-DFZ3HOPQ',
                'gun': 'https://www.youtube.com/watch?v=-LgEvQuyDxE',
                'queue': 'https://www.youtube.com/watch?v=WPkMUU9tUqk',
                'ldrizzy': 'https://www.youtube.com/watch?v=AF2MqFnPotc'}

        if egg in urls:
            await message.channel.send(urls[egg])

    async def get_current_song():
        """
        Get the current song from beatbot and return it.
        """

        async with aiohttp.ClientSession() as session:
            response = await session.get('{}now_playing'.format(
                config.SITE_URL))

            if response.status == 200:
                return (await response.json())['currentsong']
            else:
                Beatbot.log_to_file('Could not contact {}'.format(
                    config.SITE_URL))
                return None

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

@beatbot.tree.command(name='start')
async def start(interaction: discord.Interaction):
    """Join your voice channel and start playing music"""

    reply = await beatbot.start_stream(interaction.user)
    await interaction.response.send_message(reply)

@beatbot.tree.command(name='stop')
async def stop(interaction: discord.Interaction):
    """Stop playing music and leave your voice channel"""

    reply = await beatbot.stop_stream(interaction.user)
    await interaction.response.send_message(reply)

@beatbot.tree.command(name='status')
async def status(interaction: discord.Interaction):
    """Show current playing song"""

    reply = await Beatbot.get_status_embed()
    await interaction.response.send_message(embed=reply)

@beatbot.tree.command(name='search')
async def search(interaction: discord.Interaction, query: str):
    """Search for a song to play"""

    reply = await Beatbot.search_for_songs(query)
    await interaction.response.send_message(embed=reply)

@beatbot.tree.command(name='queue')
async def queue(interaction: discord.Interaction, song_id: int):
    """Queue the song with the given id number"""

    reply = await Beatbot.queue_request(song_id)
    await interaction.response.send_message(embed=reply)

beatbot.run(config.LOGIN_TOKEN)
