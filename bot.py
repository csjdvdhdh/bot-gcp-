import telebot
import os
import subprocess
import time
import queue
import threading

TOKEN = os.environ.get("BOT_TOKEN", "8761797597:AAHAmLwasf_g1fzGrXYqew7IAQG6DZNwRCI")
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 8650707600

user_state = {}
user_usage = {}
premium_users = set()
all_users = set()

# ====== نظام الطابور ======
processing_queue = queue.Queue()
is_processing = False

def get_queue_position(user_id):
    items = list(processing_queue.queue)
    for i, item in enumerate(items):
        if item['user_id'] == user_id:
            return i + 1
    return None

# ====== التحقق من الحد اليومي ======
def can_use(user_id):
    if user_id == ADMIN_ID or user_id in premium_users:
        return True
    now = time.time()
    data = user_usage.get(user_id, {"count": 0, "time": now})
    if now - data.get("time", now) > 86400:
        user_usage[user_id] = {"count": 0, "time": now}
        return True
    return data["count"] < 2

def add_usage(user_id):
    now = time.time()
    data = user_usage.get(user_id, {"count": 0, "time": now})
    if now - data.get("time", now) > 86400:
        data = {"count": 0, "time": now}
    data["count"] += 1
    user_usage[user_id] = data

def get_usage_count(user_id):
    now = time.time()
    data = user_usage.get(user_id, {"count": 0, "time": now})
    if now - data.get("time", now) > 86400:
        return 0
    return data["count"]

# ====== معالجة الكرومة مع صورة ======
def process_chroma_task(task):
    user_id = task['user_id']
    video_path = task['video_path']
    bg_path = task['bg_path']
    output_path = f"output_{user_id}.mp4"
    chat_id = task['chat_id']

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-loop", "1", "-i", bg_path,
            "-filter_complex",
            "[1:v]scale=720:1280,format=yuv420p[bg];"
            "[0:v]scale=720:-1,colorkey=black:0.3:0.1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-maxrate", "2M",
            "-bufsize", "4M",
            "-c:a", "aac",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(output_path, "rb") as v:
                    bot.send_video(
                        chat_id, v,
                        caption="✅ تم إنشاء الفيديو بنجاح!",
                        timeout=120
                    )
                break
            except Exception as send_err:
                if attempt < max_retries - 1:
                    bot.send_message(chat_id, f"⏳ جاري إعادة المحاولة ({attempt+2}/{max_retries})...")
                    time.sleep(5)
                else:
                    raise send_err

        add_usage(user_id)

    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {e}")
    finally:
        for f in [video_path, bg_path, output_path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        user_state.pop(user_id, None)

# ====== معالجة الكرومة مع فيديو ======
def process_mute_video_task(task):
    user_id = task['user_id']
    video_path = task['video_path']
    chroma_path = task['chroma_path']
    output_path = f"output_mute_{user_id}.mp4"
    muted_path = f"muted_{user_id}.mp4"
    chat_id = task['chat_id']

    try:
        # حذف الصوت من فيديو الخلفية
        mute_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-an", "-c:v", "copy",
            muted_path
        ]
        subprocess.run(mute_cmd, check=True, capture_output=True)

        # دمج الكرومة على الفيديو الصامت
        cmd = [
            "ffmpeg", "-y",
            "-i", muted_path,
            "-i", chroma_path,
            "-filter_complex",
            "[0:v]scale=720:1280,format=yuv420p[bg];"
            "[1:v]scale=720:-1,colorkey=black:0.3:0.1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-maxrate", "2M",
            "-bufsize", "4M",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(output_path, "rb") as v:
                    bot.send_video(
                        chat_id, v,
                        caption="✅ تم دمج الكرومة على الفيديو! (بدون صوت)",
                        timeout=120
                    )
                break
            except Exception as send_err:
                if attempt < max_retries - 1:
                    bot.send_message(chat_id, f"⏳ جاري إعادة المحاولة ({attempt+2}/{max_retries})...")
                    time.sleep(5)
                else:
                    raise send_err

        add_usage(user_id)

    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {e}")
    finally:
        for f in [video_path, chroma_path, output_path, muted_path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        user_state.pop(user_id, None)

# ====== معالج الطابور ======
def process_queue():
    global is_processing
    while True:
        try:
            task = processing_queue.get(timeout=1)
            is_processing = True
            user_id = task['user_id']

            try:
                bot.send_message(user_id, "🎬 دورك الآن! جاري إنشاء الفيديو...")
            except:
                pass

            if task['type'] == 'chroma':
                process_chroma_task(task)
            elif task['type'] == 'mute_video':
                process_mute_video_task(task)

            is_processing = False
            processing_queue.task_done()

            # إخطار التالي في الطابور
            if not processing_queue.empty():
                next_items = list(processing_queue.queue)
                if next_items:
                    next_user = next_items[0]['user_id']
                    try:
                        bot.send_message(next_user, "⏰ اقترب دورك! أنت الأول في الطابور")
                    except:
                        pass

        except queue.Empty:
            is_processing = False
            continue
        except Exception as e:
            print(f"Queue error: {e}")
            is_processing = False

def add_to_queue(task):
    processing_queue.put(task)
    pos = get_queue_position(task['user_id'])
    return pos if pos else processing_queue.qsize()

# ====== تشغيل الطابور ======
queue_thread = threading.Thread(target=process_queue, daemon=True)
queue_thread.start()

# ============================
# ======= أوامر المستخدم =====
# ============================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    bot.reply_to(message,
"""👋 أهلاً بك في بوت الكرومة!

📌 الطريقة:
1️⃣ اختر الوضع عبر /mode
2️⃣ أرسل فيديو الكرومة (خلفية سوداء)
3️⃣ أرسل صورة أو فيديو كخلفية

🎯 الحد اليومي: 2 فيديو مجاناً
📥 حمل كرومة من: @VjBoT

الأوامر:
/mode - اختر نوع المعالجة
/status - حالتك الحالية
/queue - مكانك في الطابور""")

@bot.message_handler(commands=['mode'])
def choose_mode(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("🖼️ صورة كخلفية", callback_data="mode_image"),
        telebot.types.InlineKeyboardButton("🎬 فيديو كخلفية", callback_data="mode_video")
    )
    bot.reply_to(message, "اختر نوع المعالجة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def handle_mode(call):
    user_id = call.from_user.id
    mode = call.data.split("_")[1]
    bot.answer_callback_query(call.id)

    if mode == "image":
        user_state[user_id] = {"mode": "image", "step": "waiting_chroma"}
        bot.send_message(call.message.chat.id,
            "✅ وضع: صورة كخلفية\n📹 أرسل الآن فيديو الكرومة (خلفية سوداء)")
    elif mode == "video":
        user_state[user_id] = {"mode": "video", "step": "waiting_bg_video"}
        bot.send_message(call.message.chat.id,
            "✅ وضع: فيديو كخلفية\n🎬 أرسل أولاً فيديو الخلفية (سيُحذف صوته)")

@bot.message_handler(commands=['status'])
def status(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    count = get_usage_count(user_id)
    is_premium = user_id in premium_users or user_id == ADMIN_ID
    text = f"""📊 حالتك:
{'👑 مميز - بدون حد' if is_premium else f'📹 الاستخدام اليوم: {count}/2'}
👥 إجمالي المستخدمين: {len(all_users)}"""
    bot.reply_to(message, text)

@bot.message_handler(commands=['queue'])
def queue_status(message):
    user_id = message.from_user.id
    pos = get_queue_position(user_id)
    size = processing_queue.qsize()
    if pos:
        bot.reply_to(message, f"📋 مكانك في الطابور: {pos}/{size}")
    else:
        bot.reply_to(message, f"✅ لست في الطابور\n👥 في الطابور حالياً: {size}")

# ====== استقبال الفيديو ======
@bot.message_handler(content_types=['video'])
def handle_video(message):
    user_id = message.from_user.id
    all_users.add(user_id)

    if not can_use(user_id):
        bot.reply_to(message, "❌ وصلت للحد اليومي (2 فيديو)\nتجدد الحد كل 24 ساعة")
        return

    if message.video.file_size > 50 * 1024 * 1024:
        bot.reply_to(message, "❌ الفيديو كبير جداً (الحد الأقصى 50MB)")
        return

    state = user_state.get(user_id, {})

    # استقبال فيديو الخلفية (وضع فيديو)
    if state.get("mode") == "video" and state.get("step") == "waiting_bg_video":
        bot.reply_to(message, "⏳ جاري تحميل فيديو الخلفية...")
        file_info = bot.get_file(message.video.file_id)
        file = bot.download_file(file_info.file_path)
        video_path = f"bg_video_{user_id}.mp4"
        with open(video_path, "wb") as f:
            f.write(file)
        user_state[user_id]["bg_video"] = video_path
        user_state[user_id]["step"] = "waiting_chroma_for_video"
        bot.reply_to(message, "✅ تم استلام فيديو الخلفية\n📹 أرسل الآن فيديو الكرومة (خلفية سوداء)")
        return

    # استقبال فيديو الكرومة (وضع فيديو - المرحلة الثانية)
    if state.get("mode") == "video" and state.get("step") == "waiting_chroma_for_video":
        bot.reply_to(message, "⏳ جاري تحميل فيديو الكرومة...")
        file_info = bot.get_file(message.video.file_id)
        file = bot.download_file(file_info.file_path)
        chroma_path = f"chroma_{user_id}.mp4"
        with open(chroma_path, "wb") as f:
            f.write(file)

        task = {
            'type': 'mute_video',
            'user_id': user_id,
            'chat_id': message.chat.id,
            'video_path': state["bg_video"],
            'chroma_path': chroma_path
        }
        pos = add_to_queue(task)
        size = processing_queue.qsize()
        if size > 1:
            bot.reply_to(message, f"✅ تم استلام الكرومة\n📋 مكانك في الطابور: {pos}/{size}\nسيتم إخطارك عند دورك 🔔")
        else:
            bot.reply_to(message, "✅ تم استلام الكرومة\n⏳ جاري المعالجة...")
        return

    # استقبال فيديو الكرومة (وضع صورة)
    if state.get("mode") == "image" and state.get("step") == "waiting_chroma":
        bot.reply_to(message, "⏳ جاري تحميل فيديو الكرومة...")
        file_info = bot.get_file(message.video.file_id)
        file = bot.download_file(file_info.file_path)
        video_path = f"video_{user_id}.mp4"
        with open(video_path, "wb") as f:
            f.write(file)
        user_state[user_id]["video"] = video_path
        user_state[user_id]["step"] = "waiting_image"
        bot.reply_to(message, "✅ تم استلام فيديو الكرومة\n🖼️ أرسل الآن صورة الخلفية")
        return

    # لم يختر وضعاً بعد
    if not state:
        bot.reply_to(message, "❌ اختر الوضع أولاً عبر /mode")

# ====== استقبال الصورة ======
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    all_users.add(user_id)

    state = user_state.get(user_id, {})

    if not state or state.get("step") != "waiting_image":
        bot.reply_to(message, "❌ اختر الوضع أولاً عبر /mode وأرسل فيديو الكرومة")
        return

    if not can_use(user_id):
        bot.reply_to(message, "❌ وصلت للحد اليومي (2 فيديو)")
        return

    bot.reply_to(message, "⏳ جاري تحميل الصورة...")
    file_info = bot.get_file(message.photo[-1].file_id)
    file = bot.download_file(file_info.file_path)
    image_path = f"image_{user_id}.jpg"
    with open(image_path, "wb") as f:
        f.write(file)

    task = {
        'type': 'chroma',
        'user_id': user_id,
        'chat_id': message.chat.id,
        'video_path': state["video"],
        'bg_path': image_path
    }
    pos = add_to_queue(task)
    size = processing_queue.qsize()
    if size > 1:
        bot.reply_to(message, f"✅ تم استلام الصورة\n📋 مكانك في الطابور: {pos}/{size}\nسيتم إخطارك عند دورك 🔔")
    else:
        bot.reply_to(message, "✅ تم استلام الصورة\n⏳ جاري إنشاء الفيديو...")

# ============================
# ====== أوامر الأدمن ======
# ============================

def is_admin(message):
    return message.from_user.id == ADMIN_ID

@bot.message_handler(commands=['admin'])
def admin_help(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    bot.reply_to(message, """👑 أوامر الأدمن:

📊 /stats - إحصائيات البوت
📢 /broadcast [رسالة] - إرسال للجميع
➕ /addpremium [id] - إضافة مميز
➖ /removepremium [id] - إزالة مميز
📋 /listpremium - قائمة المميزين""")

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    total = len(all_users)
    premium = len(premium_users)
    queue_size = processing_queue.qsize()
    active_today = sum(
        1 for uid, data in user_usage.items()
        if time.time() - data.get("time", 0) < 86400 and data.get("count", 0) > 0
    )
    text = f"""📊 إحصائيات البوت:

👥 إجمالي المستخدمين: {total}
👑 المستخدمون المميزون: {premium}
🟢 نشطون اليوم: {active_today}
📋 في الطابور الآن: {queue_size}
⚙️ جاري المعالجة: {'نعم' if is_processing else 'لا'}"""
    bot.reply_to(message, text)

@bot.message_handler(commands=['addpremium'])
def add_premium(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ الاستخدام: /addpremium [user_id]")
        return
    try:
        target_id = int(parts[1])
        premium_users.add(target_id)
        bot.reply_to(message, f"✅ تم إضافة {target_id} كمستخدم مميز")
        try:
            bot.send_message(target_id, "🎉 تم ترقيتك إلى مستخدم مميز!\nيمكنك الآن استخدام البوت بدون حد يومي 👑")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ معرف المستخدم يجب أن يكون رقماً")

@bot.message_handler(commands=['removepremium'])
def remove_premium(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ الاستخدام: /removepremium [user_id]")
        return
    try:
        target_id = int(parts[1])
        premium_users.discard(target_id)
        bot.reply_to(message, f"✅ تم إزالة {target_id} من المستخدمين المميزين")
    except ValueError:
        bot.reply_to(message, "❌ معرف المستخدم يجب أن يكون رقماً")

@bot.message_handler(commands=['listpremium'])
def list_premium(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    if not premium_users:
        bot.reply_to(message, "لا يوجد مستخدمون مميزون حالياً")
        return
    text = "👑 المستخدمون المميزون:\n" + "\n".join(f"• {uid}" for uid in premium_users)
    bot.reply_to(message, text)

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ هذا الأمر للأدمن فقط")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ الاستخدام: /broadcast [الرسالة]")
        return
    text = parts[1]
    success = 0
    failed = 0
    bot.reply_to(message, f"📤 جاري الإرسال لـ {len(all_users)} مستخدم...")
    for uid in all_users.copy():
        try:
            bot.send_message(uid, f"📢 رسالة من الإدارة:\n\n{text}")
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    bot.send_message(message.chat.id, f"✅ تم الإرسال:\n✔️ نجح: {success}\n❌ فشل: {failed}")

print("Bot is running...")
# Delete any existing webhook before starting long-polling
bot.delete_webhook()
bot.infinity_polling()
