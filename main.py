import os
import logging
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
RENDER_URL = "https://mian-bot.onrender.com"

# កំណត់ Agent សម្រាប់ស្វែងរក
search = TavilySearchResults(tavily_api_key=TAVILY_API_KEY)

# ប្រើប្រាស់ខួរក្បាល Google Gemini (ជំនាន់ថ្មី 2.5-flash ដែលមានសមត្ថភាពអានរូបភាពច្បាស់)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
agent_executor = create_react_agent(llm, [search])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="សួស្តី! ខ្ញុំជាជំនួយការ AI របស់អ្នក។ អ្នកអាចសួរសំណួរ ឬផ្ញើរូបភាពមកខ្ញុំ ដើម្បីឱ្យខ្ញុំជួយពិនិត្យបានណា៎! 🖼️✨")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    prompt = f"សំណួរ៖ {user_text}។ សូមឆ្លើយដោយស្វែងរកព័ត៌មានពីអ៊ីនធឺណិត និងដាក់លីងយោងឱ្យបានច្បាស់លាស់ជាភាសាខ្មែរ។"
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ កំពុងស្វែងរកចម្លើយ...")
    
    try:
        response = await asyncio.to_thread(agent_executor.invoke, {"messages": [("user", prompt)]})
        raw_content = response["messages"][-1].content
        
        if isinstance(raw_content, list):
            final_answer = "\n".join([str(block.get("text", "")) for block in raw_content if isinstance(block, dict)])
        else:
            final_answer = str(raw_content)
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_answer)
    except Exception as e:
        logging.error(f"Error occurred in text handle: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស មានបញ្ហាបច្ចេកទេសបន្តិចបន្តួច សូមសាកល្បងម្តងទៀត។")

# មុខងារថ្មី៖ ទទួល និងអានរូបភាព
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ចាប់យកអក្សរដែលសរសេរភ្ជាប់ជាមួយរូបភាព (Caption)
    caption = update.message.caption or "តើរូបភាពនេះបង្ហាញពីអ្វីដែរ?"
    prompt = f"សំណួរ៖ {caption}។ សូមពិនិត្យមើលរូបភាពនេះ និងឆ្លើយជាភាសាខ្មែរឱ្យបានក្បោះក្បាយ។"
    
    processing_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="👁️ កំពុងពិនិត្យមើលរូបភាព...")
    
    try:
        # ទាញយករូបភាពទំហំធំបំផុតពី Telegram
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # បំប្លែងរូបភាពទៅជា Base64 សម្រាប់បញ្ជូនទៅ Gemini
        img_base64 = base64.b64encode(photo_bytes).decode('utf-8')
        
        # រៀបចំទម្រង់សារ (Multimodal) ដើម្បីបញ្ជូនទាំងរូបភាព និងអត្ថបទ
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
            ]
        )
        
        # បញ្ជូនទៅកាន់ Agent 
        response = await asyncio.to_thread(agent_executor.invoke, {"messages": [message]})
        raw_content = response["messages"][-1].content
        
        if isinstance(raw_content, list):
            final_answer = "\n".join([str(block.get("text", "")) for block in raw_content if isinstance(block, dict)])
        else:
            final_answer = str(raw_content)
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_answer)
        
    except Exception as e:
        logging.error(f"Error occurred in photo handle: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_msg.message_id, text="សូមទោស ខ្ញុំមានបញ្ហាក្នុងការអានរូបភាពនេះ សូមព្យាយាមម្ដងទៀត។")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    # សម្រាប់ទទួលសារជាអក្សរ
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    # សម្រាប់ទទួលរូបភាព (បន្ថែមថ្មី)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=f"{RENDER_URL}/telegram",
        drop_pending_updates=True
    )
