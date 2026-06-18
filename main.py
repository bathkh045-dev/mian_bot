import os
import logging
import asyncio
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

# កំណត់ប្រព័ន្ធ Log សម្រាប់តាមដានបញ្ហា
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
RENDER_URL = "https://mian-bot.onrender.com"  # ត្រូវប្រាកដថា URL នេះត្រូវនឹង Render របស់អ្នក

# ១. បង្កើត Instant សម្រាប់ LLM និង Agent
search = TavilySearchResults(tavily_api_key=TAVILY_API_KEY)
# ប្រើ gemini-2.5-flash សម្រាប់អានរូបភាព និងឆ្លើយសំណួរទូទៅ
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
agent_executor = create_react_agent(llm, [search])

# បង្កើត Application របស់ Telegram
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# --- ផ្នែកគ្រប់គ្រងមុខងាររបស់ Bot ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="សួស្តី! ខ្ញុំជាជំនួយការ AI របស់អ្នក។ អ្នកអាចសួរសំណួរ ឬផ្ញើរូបភាពមកខ្ញុំ ដើម្បីឱ្យខ្ញុំជួយពិនិត្យបានណា៎! 🖼️✨"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    prompt = f"សំណួរ៖ {user_text}។ សូមឆ្លើយដោយស្វែងរកព័ត៌មានពីអ៊ីនធឺណិត និងដាក់លីងយោងឱ្យបានច្បាស់លាស់ជាភាសាខ្មែរ។"
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ កំពុងស្វែងរកចម្លើយ...")
    
    try:
        response = await asyncio.to_thread(agent_executor.invoke, {"messages": [("user", prompt)]})
        raw_content = response["messages"][-1].content
        
        final_answer = "\n".join([str(block.get("text", "")) for block in raw_content if isinstance(block, dict)]) if isinstance(raw_content, list) else str(raw_content)
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_answer)
    except Exception as e:
        logger.error(f"Error in text handle: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស មានបញ្ហាបច្ចេកទេសបន្តិចបន្តួច សូមសាកល្បងម្តងទៀត។")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or "តើរូបភាពនេះបង្ហាញពីអ្វីដែរ?"
   photo_file = await update.message.photo[-1].get_file()
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="👁️ កំពុងពិនិត្យមើលរូបភាព...")
    
   photo_bytes = await photo_file.download_as_bytearray()
img_base64 = base64.b64encode(photo_bytes).decode('utf-8')
       message = HumanMessage(
    content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
    ]
)
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
            ]
        )
        
        # ហៅប្រើប្រាស់ LLM ផ្ទាល់សម្រាប់អានរូបភាព
        response = await asyncio.to_thread(llm.invoke, [message])
        final_answer = str(response.content)
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_answer)
        
    except Exception as e:
        logger.error(f"Error in photo handle: {e}")
        try:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស ខ្ញុំមានបញ្ហាក្នុងការអានរូបភាពនេះ សូមព្យាយាមម្ដងទៀត។")
        except Exception:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="សូមទោស ខ្ញុំមានបញ្ហាក្នុងការអានរូបភាពនេះ សូមព្យាយាមម្ដងទៀត។")

# --- ផ្នែករៀបចំ FastAPI Webhook Server សម្រាប់ Render ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ដំឡើង Handlers ទៅឱ្យ Telegram Application
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # ផ្ដើមដំណើរការប្រព័ន្ធ Telegram
    await telegram_app.initialize()
    await telegram_app.start()
    
    # កំណត់កំណត់ Webhook ទៅកាន់ Telegram Server
    webhook_url = f"{RENDER_URL}/telegram"
    logger.info(f"Setting webhook to: {webhook_url}")
    await telegram_app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    
    yield
    
    # បិទប្រព័ន្ធនៅពេលឈប់ដំណើរការ Server
    await telegram_app.stop()
    await telegram_app.shutdown()

# បង្កើត Web Server
app = FastAPI(lifespan=lifespan)

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """ទទួលទិន្នន័យពី Telegram រួចបញ្ជូនទៅឱ្យ python-telegram-bot ចាត់ចែង"""
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, telegram_app.bot)
        await telegram_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def root():
    return {"status": "Bot is running perfectly!"}

# --- ផ្នែកបន្ថែមថ្មីនៅខាងក្រោមបង្អស់ដើម្បីដុតបញ្ឆេះ Server (ជួរទី ១២៨) ---
if __name__ == '__main__':
    import uvicorn
    # ទាញយក Port ពី Render ប្រសិនបើគ្មានវាដកយក Port 10000 ជាលំនាំដើម
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting uvicorn server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port)
