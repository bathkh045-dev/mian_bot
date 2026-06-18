import os
import logging
import asyncio
import base64
import io  # ថែមថ្មីសម្រាប់ជំនួយការទាញយករូបភាព
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
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស មានបញ្ហាបច្គេកទេសបន្តិចបន្តួច សូមសាកល្បងម្តងទៀត។")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or "តើរូបភាពនេះបង្ហាញពីអ្វីដែរ?"
    prompt = f"សំណួរ៖ {caption} ចូលពិនិត្យមើលរូបភាពនេះ និងឆ្លើយតបជាភាសាខ្មែរឱ្យបានក្បោះក្បាយលម្អិត។"
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="👁️ កំពុងពិនិត្យមើលរូបភាព...")
    
    try:
        # ទាញយករូបភាពទំហំធំបំផុត
        photo_file = await update.message.photo[-1].get_file()
        
        # កែប្រែ៖ ទាញយកជាប្រភេទ Bytes តាមរយៈ Memory buffer (BytesIO) ជៀសវាងការគាំង Error
        out = io.BytesIO()
        await photo_file.download_to_memory(out)
        img_base64 = base64.b64encode(out.getvalue()).decode('utf-8')
        
        # កែប្រែ៖ រៀបចំទម្រង់ image_url ឱ្យត្រូវតាមស្តង់ដារ LangChain-Google
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{img_base64}"}
            ]
        )
        
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
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    await telegram_app.initialize()
    await telegram_app.start()
    
    webhook_url = f"{RENDER_URL}/telegram"
    logger.info(f"Setting webhook to: {webhook_url}")
    await telegram_app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    
    yield
    
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/telegram")
async def telegram_webhook(request: Request):
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, telegram_app.bot)
        
        # កែប្រែ៖ ប្រើ asyncio.create_task ដើម្បីឱ្យ Webhook ឆ្លើយតបទៅ Telegram វិញភ្លាមៗ (កុំឱ្យទាក់)
        asyncio.create_task(telegram_app.process_update(update))
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def root():
    return {"status": "Bot is running perfectly!"}

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting uvicorn server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port)
