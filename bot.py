import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

# دالة للرد على أمر start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أرسل لي رابط Google Cloud للبدء.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("⏳ بدأت العملية، سأرسل لك التحديثات...")

    # تشغيل الأتمتة
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            
            # مرحلة 1: الموافقة
            page.wait_for_selector("button:has-text('أفهم ذلك'), button:has-text('Understand')", timeout=30000)
            page.screenshot(path="step1.png")
            await context.bot.send_photo(chat_id=chat_id, photo=open("step1.png", "rb"), caption="تم الضغط على أفهم ذلك")
            page.click("button:has-text('أفهم ذلك'), button:has-text('Understand')")

            # مرحلة 2: شروط الخدمة
            page.wait_for_selector("button:has-text('Agree and continue')", timeout=30000)
            page.click("input[type='checkbox']") # الموافقة على المربع
            page.screenshot(path="step2.png")
            await context.bot.send_photo(chat_id=chat_id, photo=open("step2.png", "rb"), caption="تمت الموافقة على الشروط")
            page.click("button:has-text('Agree and continue')")

            # مرحلة 3: القائمة و Cloud Run
            page.wait_for_selector("text=Cloud Run", timeout=40000)
            page.screenshot(path="step3.png")
            await context.bot.send_photo(chat_id=chat_id, photo=open("step3.png", "rb"), caption="تم الوصول لقائمة Cloud Run")
            page.click("text=Cloud Run")
            
            # (يمكنك إضافة باقي الخطوات هنا بنفس النمط)

            browser.close()
            await update.message.reply_text("✅ تمت المهمة بنجاح!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")

if __name__ == '__main__':
    TOKEN = os.getenv("8713607063:AAGp5pXAOZkOt9DS33oA-HZp3OT9rNHfFZk")
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_polling()

