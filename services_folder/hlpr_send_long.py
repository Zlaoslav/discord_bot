import discord
from discord.ext import commands

def _chunk_text(text: str, size: int = 1900) -> list:
    return [text[i:i+size] for i in range(0, len(text), size)] if text else []

async def _send_long_followup(interaction: discord.Interaction, text: str) -> None:
    """Send long text via interaction.followup, splitting into 1900-char chunks."""
    chunks = _chunk_text(text, 1900)
    for chunk in chunks:
        if chunk.strip():
            await interaction.followup.send(chunk, ephemeral=False)
            
async def _send_long_ctx(ctx: commands.Context, text: str) -> None:
    """Send long text via ctx.send, splitting into 1900-char chunks."""
    chunks = _chunk_text(text, 1900)
    for chunk in chunks:
        await ctx.send(chunk)