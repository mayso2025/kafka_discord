import asyncio
import nextcord
from nextcord.ext import commands
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import logging
import logging.config
from aiohttp import ClientSession, BasicAuth
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough

# Logging Configuration
logging_config = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'INFO'
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'app.log',
            'formatter': 'default',
            'level': 'DEBUG'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}

DATA_PATH = "discord_bot\data\stuff\output.md"

# Configure logging
logging.config.dictConfig(logging_config)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    announcement_channel_id: int 
    discord_token: str 
    openai_api_key: str 

    class Config:
        env_file = ".env"

settings = Settings()

class MessageModel(BaseModel):
    content: str
    author_id: str
    channel_id: str
    guild_id: str = None
    attachments: list = []

intents = nextcord.Intents.default()
intents.messages = True  # This is critical to enable if using message content
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Setup LangChain with OpenAI
chat_api = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-3.5-turbo")
logger.info("Chat API initialized with model gpt-3.5-turbo")

async def upload_files(attachments):
    urls = []
    async with ClientSession() as session:
        for attachment in attachments:
            content = await attachment.read()
            url = f"https://minio.example.com/{attachment.filename}"
            auth = BasicAuth(login="minioadmin", password="minioadmin")
            async with session.put(url, data=content, auth=auth) as response:
                if response.status == 200:
                    logger.info(f"File uploaded successfully: {url}")
                    urls.append(url)
                else:
                    logger.error(f"Failed to upload file to MinIO: {response.status}")
    return urls

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    channel = bot.get_channel(settings.announcement_channel_id)
    if channel:
        logger.info(f"Sending greeting message to channel {settings.announcement_channel_id}")
        await channel.send("Greetings traveler! Welcome to the Steampunk City of London!")
    else:
        logger.warning(f"Channel with ID {settings.announcement_channel_id} not found.")

@bot.slash_command(description="Echo the provided message")
async def echo(ctx, *, message: str):
    await ctx.send(message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        logger.debug("Received message from self, ignoring")
        return

    attachments_urls = await upload_files(message.attachments) if message.attachments else []
    prompt_text = f"You are a DND dungeon master, give the player an amazing adventure in a time set where Steampunk machines reigned supreme in the city of London! Give the player a scenario could be funny, serious or normal and ask them to roll a d20 dice when they say they want to do something. BEFORE GIVING ANOTHER PROMPT, let them answer first. Based on what they said they rolled, respond accordingly. (1 being a low roll and 20 being a guarenteed action). Between each scenario, storytell about the surroundings of the city.'{message.content}'"
    prompt = ChatPromptTemplate.from_messages([("system", prompt_text)])
    logger.info("Generating response using Chat API")

    chain = (
        RunnablePassthrough.assign(
            input=lambda x: x["input"]
        )
        | prompt
        | chat_api
        | StrOutputParser()
    )

    try:
        response = await chain.ainvoke({"input": message.content})
        logger.info("Response generated successfully")
        response_message = f"The Floating Gear Man: {response}"
        await message.channel.send(response_message)
        logger.info(f"Generated response: {response}")
    except Exception as e:
        logger.error(f"Failed to generate response: {e}")
        await message.channel.send("Sorry, I encountered an error. Please try asking something else.")

    if isinstance(message.channel, nextcord.DMChannel):
        logger.debug("Processing message in DM channel")
    elif isinstance(message.channel, nextcord.abc.GuildChannel):
        logger.debug(f"Processing message in guild channel: {message.channel.guild.name}")
    else:
        logger.warning(f"Unsupported channel type: {type(message.channel)}")

async def start():
    try:
        logger.info("Starting Discord bot...")
        await bot.start(settings.discord_token)
    except Exception as e:
        logger.error(f"Failed to start services due to: {e}")
    finally:
        await stop()

async def stop():
    logger.info("Stopping Discord bot...")
    await bot.close()
    logger.info("Discord bot stopped")

if __name__ == "__main__":
    asyncio.run(start())