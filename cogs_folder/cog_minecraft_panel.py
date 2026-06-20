from bot import Bot
import discord
from discord.ext import commands, tasks
from discord import app_commands
from services_folder.srv_minecraft_panel import create_send_save_minecraft_panel, create_minecraft_panel
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

class minecraft_panel(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="send_minecraft_panel",
        description="Создать панель сервера"
    )
    async def send_minecraft_panel(
        self,
        interaction: discord.Interaction,
        ip: str,
        real_ip: str | None = None,
        port: int = 25565,
        query_port: int | None = None
    ):
        # Проверка прав
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)  # отвечаем только пользователю

        if real_ip is None:
            real_ip = ip  # если реальный IP не указан, берем ip сервера

        embed, view = await create_send_save_minecraft_panel(
            self.bot, interaction, ip, real_ip, port, query_port
        )

        # Отправляем панель в канал (видимую всем)
        msg = await interaction.channel.send(embed=embed, view=view)

        # Обновляем данные view (guild_id и message_id)
        view.guild_id = interaction.guild_id
        view.message_id = msg.id

        await self.bot.db.minecraft_panel.add_minecraft_panel(
            guild_id=interaction.guild_id,
            server_ip=ip,
            real_ip=real_ip,
            server_port=port,
            query_port=query_port,
            channel_id=interaction.channel.id,
            message_id=msg.id
        )

        # Если таск обновления не запущен — запускаем
        if not self.update_panels_task.is_running():
            self.update_panels_task.start()

        # Отправляем пользователю ephemeral-сообщение о успехе
        await interaction.followup.send("✅ Панель успешно отправлена!", ephemeral=True)


    @commands.Cog.listener()
    async def on_ready(self):
        if not self.update_panels_task.is_running():
            self.update_panels_task.start()

    @tasks.loop(seconds=30)
    async def update_panels_task(self):
        """
        Обновляет все панели в Discord каждые 30 секунд.
        Использует новую базу minecraft_panels_v3 с real_ip.
        """
        panels = await self.bot.db.minecraft_panel.get_all_panels()

        for guild_id, server_ip, real_ip, port, query_port, channel_id, message_id in panels:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(message_id)
                embed, view = await create_minecraft_panel(server_ip, real_ip, port, query_port, self.bot, guild_id, message_id)

                # Обновляем guild_id и message_id у view
                view.guild_id = guild_id
                view.message_id = message_id

                await message.edit(embed=embed, view=view)

            except discord.NotFound:
                # Удаляем запись из БД, если сообщение удалено
                await self.bot.db.minecraft_panel.delete_minecraft_panel(int(message_id))
                logger.info(f"[PANEL REMOVE] {server_ip}:{port} — сообщение удалено")

            except discord.Forbidden:
                pass

            except Exception as e:
                pass


async def setup(bot: Bot):
    await bot.add_cog(minecraft_panel(bot))
