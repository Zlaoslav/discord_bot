from bot import Bot

import discord
from discord.ext import commands
from discord.ext import voice_recv


class MySink(voice_recv.AudioSink):
    def __init__(
        self,
        bot: Bot,
        first_channel_id: int,
        second_channel_id: int,
        first_voice_client: discord.VoiceClient,
        second_voice_client: discord.VoiceClient,
    ):
        super().__init__()

        self.bot = bot
        self.first_channel_id = first_channel_id
        self.second_channel_id = second_channel_id
        self.first_voice_client = first_voice_client
        self.second_voice_client = second_voice_client

    def wants_opus(self) -> bool:
        return False

    def cleanup(self):
        print("Sink cleaned up")

    def write(self, user, data):
        if user is None:
            return

        if data is None:
            return

        if data.pcm is None:
            return

        if self.bot.user and user.id == self.bot.user.id:
            return

        if user.voice is None:
            return

        if user.voice.channel is None:
            return

        pcm = data.pcm

        print(f"Receiving {len(pcm)} bytes from {user}")

        try:
            if (
                user.voice.channel.id == self.first_channel_id
                and self.second_voice_client.is_connected()
            ):
                self.second_voice_client.send_audio_packet(
                    pcm,
                    encode=True,
                )

            elif (
                user.voice.channel.id == self.second_channel_id
                and self.first_voice_client.is_connected()
            ):
                self.first_voice_client.send_audio_packet(
                    pcm,
                    encode=True,
                )

        except Exception:
            import traceback

            traceback.print_exc()


class VoiceBridge(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

        self.first_client: voice_recv.VoiceRecvClient | None = None
        self.second_client: voice_recv.VoiceRecvClient | None = None

        self.first_sink: MySink | None = None
        self.second_sink: MySink | None = None

    @commands.command()
    async def start_bridge(
        self,
        ctx: commands.Context,
        first_id: int,
        second_id: int,
        first_guild_id: int,
        second_guild_id: int,
    ):
        first_guild = self.bot.get_guild(first_guild_id)
        second_guild = self.bot.get_guild(second_guild_id)

        if first_guild is None or second_guild is None:
            await ctx.send("Guild not found.")
            return

        first_channel = first_guild.get_channel(first_id)
        second_channel = second_guild.get_channel(second_id)

        if not isinstance(first_channel, discord.VoiceChannel):
            await ctx.send("First channel is not a voice channel.")
            return

        if not isinstance(second_channel, discord.VoiceChannel):
            await ctx.send("Second channel is not a voice channel.")
            return

        try:
            self.first_client = await first_channel.connect(
                cls=voice_recv.VoiceRecvClient
            )

            self.second_client = await second_channel.connect(
                cls=voice_recv.VoiceRecvClient
            )

        except Exception as e:
            await ctx.send(f"Connect failed:\n{e}")
            return

        self.first_sink = MySink(
            self.bot,
            first_id,
            second_id,
            self.first_client,
            self.second_client,
        )

        self.second_sink = MySink(
            self.bot,
            first_id,
            second_id,
            self.first_client,
            self.second_client,
        )

        self.first_client.listen(self.first_sink)
        self.second_client.listen(self.second_sink)

        await ctx.send("Bridge started.")


    @commands.Cog.listener()
    async def on_ready(self):
        print("Voice bridge loaded")


async def setup(bot: Bot):
    await bot.add_cog(VoiceBridge(bot))