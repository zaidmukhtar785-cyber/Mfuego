import logging
import discord
import wavelink
from discord.ext import commands
from app.config import (DISCORD_BOT_TOKEN, DEFAULT_PREFIX, LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD)
from app.db import init_db, SessionLocal, get_guild_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fuegos")

async def prefix_for(bot, message):
    if message.guild is None:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot, message)
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, message.guild.id)
        prefix = cfg.prefix or DEFAULT_PREFIX
    return commands.when_mentioned_or(prefix)(bot, message)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix=prefix_for, intents=intents, help_command=None)

@bot.event
async def setup_hook():
    await init_db()
    if LAVALINK_HOST and LAVALINK_PASSWORD:
        node = wavelink.Node(uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}", password=LAVALINK_PASSWORD)
        await wavelink.Pool.connect(nodes=[node], client=bot)
        log.info("Connected to Lavalink at %s:%s", LAVALINK_HOST, LAVALINK_PORT)
    else:
        log.warning("Lavalink not configured; music commands will be unavailable until LAVALINK_HOST and LAVALINK_PASSWORD are set.")
    synced = await bot.tree.sync()
    log.info("Synced %s global slash commands", len(synced))

@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

@bot.event
async def on_member_join(member: discord.Member):
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, member.guild.id)
        if not cfg.welcome_enabled or not cfg.welcome_channel_id:
            return
        channel = member.guild.get_channel(cfg.welcome_channel_id)
        if isinstance(channel, discord.TextChannel):
            message = (cfg.welcome_message
                       .replace("{user}", member.mention)
                       .replace("{server}", member.guild.name))
            try:
                await channel.send(message[:1900])
            except discord.Forbidden:
                log.warning("Missing permission to send welcome message in guild %s", member.guild.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ You don't have permission to use that command.", mention_author=False)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.reply("❌ I don't have the required permissions.", mention_author=False)
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("❌ Invalid argument. Check the command format.", mention_author=False)
    else:
        log.exception("Command error", exc_info=error)
        try:
            await ctx.reply("⚠️ Something went wrong. The error was logged.", mention_author=False)
        except discord.HTTPException:
            pass

@bot.hybrid_command(name="ping", description="Check Fuegos bot latency")
async def ping(ctx: commands.Context):
    await ctx.reply(f"🏓 Pong! `{round(bot.latency * 1000)}ms`", mention_author=False)

@bot.hybrid_command(name="help", description="Show available Fuegos commands")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="🔥 Fuegos Commands",
        description="Use slash commands or your configured prefix.",
        color=discord.Color.blurple()
    )
    embed.add_field(name="General", value="`/ping` · `!ping` · `/help` · `!help`", inline=False)
    embed.add_field(name="Configuration", value="`/setprefix` · `/config` · `/setwelcome`", inline=False)
    embed.add_field(name="Moderation", value="`/ban` · `/clear`", inline=False)
    embed.add_field(name="Music", value="`/play` · `/skip` · `/pause` · `/resume` · `/stop` · `/queue` · `/nowplaying` · `/volume`", inline=False)
    await ctx.reply(embed=embed, mention_author=False)

@bot.hybrid_command(name="setprefix", description="Set this server's prefix")
@commands.has_guild_permissions(manage_guild=True)
async def setprefix(ctx: commands.Context, prefix: str):
    prefix = prefix.strip()
    if not 1 <= len(prefix) <= 4 or any(ch.isspace() for ch in prefix):
        await ctx.reply("Prefix must be 1–4 non-space characters.", mention_author=False)
        return
    if ctx.guild is None:
        await ctx.reply("Use this command inside a server.", mention_author=False)
        return
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, ctx.guild.id)
        cfg.prefix = prefix
        await session.commit()
    await ctx.reply(f"✅ Prefix updated to `{prefix}`.", mention_author=False)

@bot.hybrid_command(name="config", description="Show this server's Fuegos settings")
@commands.has_guild_permissions(manage_guild=True)
async def config_command(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.reply("Use this command inside a server.", mention_author=False)
        return
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, ctx.guild.id)
        embed = discord.Embed(title=f"⚙️ {ctx.guild.name} Configuration", color=discord.Color.blurple())
        embed.add_field(name="Prefix", value=f"`{cfg.prefix}`", inline=True)
        embed.add_field(name="Welcome", value="Enabled" if cfg.welcome_enabled else "Disabled", inline=True)
        embed.add_field(name="Welcome channel", value=f"<#{cfg.welcome_channel_id}>" if cfg.welcome_channel_id else "Not set", inline=True)
        await ctx.reply(embed=embed, mention_author=False)

@bot.hybrid_command(name="setwelcome", description="Configure welcome channel and message")
@commands.has_guild_permissions(manage_guild=True)
async def setwelcome(ctx: commands.Context, channel: discord.TextChannel, *, message: str = "Welcome {user} to {server}!"):
    if ctx.guild is None:
        await ctx.reply("Use this command inside a server.", mention_author=False)
        return
    if len(message) > 1800:
        await ctx.reply("Welcome message must be under 1800 characters.", mention_author=False)
        return
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, ctx.guild.id)
        cfg.welcome_channel_id = channel.id
        cfg.welcome_message = message
        cfg.welcome_enabled = True
        await session.commit()
    await ctx.reply(f"✅ Welcome messages enabled in {channel.mention}. Use `{ '{user}' }` and `{ '{server}' }` placeholders.", mention_author=False)

@bot.hybrid_command(name="ban", description="Ban a member")
@commands.has_guild_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if ctx.guild is None:
        await ctx.reply("Use this command inside a server.", mention_author=False)
        return
    if member.id == ctx.author.id or member == ctx.guild.owner:
        await ctx.reply("❌ You can't ban that member.", mention_author=False)
        return
    try:
        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason[:400]}")
        await ctx.reply(f"🔨 Banned **{member}**. Reason: {reason[:300]}", mention_author=False)
    except discord.Forbidden:
        await ctx.reply("❌ Discord denied the action. Check role hierarchy and permissions.", mention_author=False)

@bot.hybrid_command(name="clear", description="Delete recent messages")
@commands.has_guild_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clear(ctx: commands.Context, amount: int):
    if ctx.guild is None or ctx.channel is None or not isinstance(ctx.channel, discord.TextChannel):
        await ctx.reply("Use this command in a server text channel.", mention_author=False)
        return
    if not 1 <= amount <= 100:
        await ctx.reply("Choose an amount from 1 to 100.", mention_author=False)
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Deleted {max(0, len(deleted)-1)} messages.", delete_after=5)


# Lavalink/Wavelink music commands. Requires a separate Lavalink v4 service.
def get_music_player(guild: discord.Guild | None) -> wavelink.Player | None:
    if guild is None:
        return None
    player = guild.voice_client
    return player if isinstance(player, wavelink.Player) else None

@bot.hybrid_command(name="play", description="Play a song or add it to the queue")
async def play(ctx: commands.Context, *, query: str):
    if ctx.guild is None:
        await ctx.reply("Use music commands inside a server.", mention_author=False)
        return
    if not LAVALINK_HOST or not LAVALINK_PASSWORD:
        await ctx.reply("🎵 Music isn't configured yet. Set the Lavalink variables in Railway.", mention_author=False)
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.reply("Join a voice channel first.", mention_author=False)
        return
    await ctx.defer()
    try:
        tracks = await wavelink.Playable.search(query)
        if not tracks:
            await ctx.send("No tracks found. Try a different search or URL.")
            return
        track = tracks[0]
        player = get_music_player(ctx.guild)
        if player is None:
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        elif player.channel != ctx.author.voice.channel:
            await ctx.send("Join my current voice channel to add music.")
            return
        if player.playing or player.paused:
            await player.queue.put_wait(track)
            await ctx.send(f"➕ Added to queue: **{track.title}**")
        else:
            await player.play(track)
            await ctx.send(f"▶️ Now playing: **{track.title}**")
    except (wavelink.LavalinkException, discord.HTTPException) as exc:
        log.warning("Music play failed: %s", exc)
        await ctx.send("Couldn't play that track. Check Lavalink connectivity and supported sources.")
    except Exception as exc:
        log.exception("Unexpected music error: %s", exc)
        await ctx.send("Music failed unexpectedly. Check the bot logs and Lavalink service.")

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    player = payload.player
    if not isinstance(player, wavelink.Player):
        return
    if player.queue.is_empty:
        return
    try:
        next_track = await player.queue.get_wait()
        await player.play(next_track)
    except Exception:
        log.exception("Failed to play next queued track")

@bot.hybrid_command(name="skip", description="Skip the current song")
async def skip(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None or not player.playing:
        await ctx.reply("Nothing is playing.", mention_author=False)
        return
    await player.skip()
    await ctx.reply("⏭️ Skipped.", mention_author=False)

@bot.hybrid_command(name="pause", description="Pause music")
async def pause(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None or not player.playing:
        await ctx.reply("Nothing is playing.", mention_author=False)
        return
    await player.pause(True)
    await ctx.reply("⏸️ Paused.", mention_author=False)

@bot.hybrid_command(name="resume", description="Resume music")
async def resume(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None or not player.paused:
        await ctx.reply("Music isn't paused.", mention_author=False)
        return
    await player.pause(False)
    await ctx.reply("▶️ Resumed.", mention_author=False)

@bot.hybrid_command(name="stop", description="Stop music and leave voice")
async def stop(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None:
        await ctx.reply("I'm not in a voice channel.", mention_author=False)
        return
    player.queue.clear()
    await player.disconnect()
    await ctx.reply("⏹️ Stopped and disconnected.", mention_author=False)

@bot.hybrid_command(name="queue", description="Show the music queue")
async def queue_command(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None:
        await ctx.reply("Nothing is playing.", mention_author=False)
        return
    upcoming = list(player.queue)[:10]
    lines = [f"**Now:** {player.current.title}" if player.current else "**Now:** Nothing"]
    lines += [f"`{i}.` {track.title}" for i, track in enumerate(upcoming, start=1)]
    if not upcoming:
        lines.append("Queue is empty.")
    await ctx.reply(embed=discord.Embed(title="🎶 Fuegos Queue", description="\n".join(lines), color=discord.Color.blurple()), mention_author=False)

@bot.hybrid_command(name="nowplaying", description="Show the current track")
async def nowplaying(ctx: commands.Context):
    player = get_music_player(ctx.guild)
    if player is None or player.current is None:
        await ctx.reply("Nothing is playing.", mention_author=False)
        return
    await ctx.reply(embed=discord.Embed(title="🎵 Now Playing", description=f"**{player.current.title}**\n{player.current.uri or ''}", color=discord.Color.blurple()), mention_author=False)

@bot.hybrid_command(name="volume", description="Set music volume from 1 to 100")
async def volume(ctx: commands.Context, amount: int):
    player = get_music_player(ctx.guild)
    if player is None:
        await ctx.reply("I'm not playing music.", mention_author=False)
        return
    if not 1 <= amount <= 100:
        await ctx.reply("Choose a volume from 1 to 100.", mention_author=False)
        return
    await player.set_volume(amount)
    await ctx.reply(f"🔊 Volume set to **{amount}%**.", mention_author=False)


async def main():
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing. Set it in Railway variables.")
    await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
