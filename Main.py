import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
RENDER_URL = "https://my-bot-ubfg.onrender.com"

# កំណត់ Agent សម្រាប់ស្វែងរក
search = TavilySearchResults(tavily_api_key=TAVILY_API_KEY)

# ប្រើប្រាស់ខួរក្បាល Google Gemini
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
agent_executor = create_react_agent(llm, [search])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="សួស្តី! ខ្ញុំជាជំនួយការ AI របស់អ្នក (ដំណើរការដោយ Gemini)។ តើមានអ្វីឱ្យខ្ញុំជួយស្វែងរកព័ត៌មានដែរឬទេ?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    prompt = f"សំណួរ៖ {user_text}។ សូមឆ្លើយដោយស្វែងរកព័ត៌មានពីអ៊ីនធឺណិត និងដាក់លីងយោងឱ្យបានច្បាស់លាស់។"
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ កំពុងស្វែងរកចម្លើយពី Gemini...")
    
    try:
        response = await asyncio.to_thread(agent_executor.invoke, {"messages": [("user", prompt)]})
        raw_content = response["messages"][-1].content
        
        # មុខងារបំប្លែងកូដ Unicode ទៅជាអក្សរខ្មែរវិញ
        if isinstance(raw_content, list):
            final_answer = "\n".join([block.get("text", "") for block in raw_content if isinstance(block, dict)])
        else:
            final_answer = str(raw_content)
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_answer)
    except Exception as e:
        logging.error(f"Error occurred: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស មានបញ្ហាបច្ចេកទេសបន្តិចបន្តួច សូមសាកល្បងម្តងទៀត។")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=f"{RENDER_URL}/telegram",
        drop_pending_updates=True
    )
