import os
import logging
import asyncio
from dotenv import load_dotenv

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
    BotCommandScopeDefault, BotCommandScopeChat,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes,
    filters,
)

from src.database.db import init_db
from src.bot.orders import save_order, get_orders, update_order_status, register_user
from src.content.content import (
    SERVICES, PORTFOLIO, FAQ, CALC_FACTORS,
    format_services_list, format_portfolio, format_faq,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "410378918").split(",") if x.strip()]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("lotos")

# ── ConversationHandler states ──────────────────────────────────────────────
(
    ORDER_SERVICE,
    ORDER_DETAILS,
    ORDER_CONTACT,
    CALC_TYPE,
    CALC_FEATURES,
) = range(5)

MAIN_MENU_TEXT = (
    "👾 *LotOS* — разрабатываем ботов, настраиваем серверы, делаем сайты.\n\n"
    "Выбери раздел:"
)


# ── keyboards ───────────────────────────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Услуги и цены", callback_data="menu:services"),
         InlineKeyboardButton("🖼 Портфолио", callback_data="menu:portfolio")],
        [InlineKeyboardButton("📝 Оставить заявку", callback_data="menu:order"),
         InlineKeyboardButton("🧮 Калькулятор", callback_data="menu:calc")],
        [InlineKeyboardButton("❓ FAQ", callback_data="menu:faq"),
         InlineKeyboardButton("📬 Написать", url="https://t.me/Saykot")],
    ])


def kb_back(to: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data=f"menu:{to}")
    ]])


def kb_services_order() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:main"),
         InlineKeyboardButton("📝 Оставить заявку", callback_data="menu:order")],
    ])


# ── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username or "", user.full_name or "")
    await update.message.reply_text(
        MAIN_MENU_TEXT,
        reply_markup=kb_main(),
        parse_mode="Markdown",
    )


# ── /menu ────────────────────────────────────────────────────────────────────

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        MAIN_MENU_TEXT,
        reply_markup=kb_main(),
        parse_mode="Markdown",
    )


# ── /orders (admin) ──────────────────────────────────────────────────────────

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    rows = get_orders()
    if not rows:
        await update.message.reply_text("Заявок пока нет.")
        return
    lines = []
    for r in rows[:20]:
        lines.append(
            f"#{r['id']} [{r['status']}] {r['created_at'][:10]}\n"
            f"  {r['full_name']} (@{r['username']})\n"
            f"  Услуга: {r['service']}\n"
            f"  Контакт: {r['contact']}\n"
            f"  {r['details'][:100]}"
        )
    await update.message.reply_text("\n\n".join(lines))


# ── callback router ──────────────────────────────────────────────────────────

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "main":
        await query.edit_message_text(
            MAIN_MENU_TEXT,
            reply_markup=kb_main(),
            parse_mode="Markdown",
        )

    elif action == "services":
        text = "💼 *Наши услуги*\n\n" + format_services_list()
        await query.edit_message_text(text, reply_markup=kb_services_order(), parse_mode="Markdown")

    elif action == "portfolio":
        text = "🖼 *Портфолио*\n\n" + format_portfolio()
        await query.edit_message_text(text, reply_markup=kb_back(), parse_mode="Markdown",
                                      disable_web_page_preview=True)

    elif action == "faq":
        text = "❓ *Частые вопросы*\n\n" + format_faq()
        await query.edit_message_text(text, reply_markup=kb_back(), parse_mode="Markdown")

    elif action == "order":
        # Start ConversationHandler — этот callback просто показывает инструкцию,
        # реальный диалог стартует через conv_entry_order
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(s["emoji"] + " " + s["name"], callback_data=f"svc:{s['id']}")]
            for s in SERVICES
        ] + [[InlineKeyboardButton("◀️ Назад", callback_data="menu:main")]])
        await query.edit_message_text(
            "📝 *Оставить заявку*\n\nВыбери услугу:",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    elif action == "calc":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Телеграм-бот", callback_data="calc:bot"),
             InlineKeyboardButton("🌐 Сайт", callback_data="calc:site")],
            [InlineKeyboardButton("◀️ Назад", callback_data="menu:main")],
        ])
        await query.edit_message_text(
            "🧮 *Калькулятор стоимости*\n\nЧто будем считать?",
            reply_markup=kb,
            parse_mode="Markdown",
        )


# ── Заявка: ConversationHandler ──────────────────────────────────────────────

async def svc_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    svc_id = query.data.split(":", 1)[1]
    # Найти услугу
    svc = next((s for s in SERVICES if s["id"] == svc_id), None)
    context.user_data["order_service"] = svc["name"] if svc else svc_id
    await query.edit_message_text(
        f"✅ Услуга: *{context.user_data['order_service']}*\n\n"
        "Расскажи подробнее — что нужно сделать, есть ли примеры, пожелания?",
        parse_mode="Markdown",
    )
    return ORDER_DETAILS


async def order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_details"] = update.message.text
    await update.message.reply_text(
        "📬 Как с тобой связаться?\n\n"
        "Напиши Telegram @username, номер телефона или email."
    )
    return ORDER_CONTACT


async def order_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.text
    service = context.user_data.get("order_service", "?")
    details = context.user_data.get("order_details", "")

    order_id = save_order(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        service=service,
        details=details,
        contact=contact,
    )

    await update.message.reply_text(
        f"✅ Заявка #{order_id} принята!\n\n"
        "Отвечу в течение дня. Если срочно — напиши напрямую: @Saykot",
        reply_markup=kb_main(),
    )

    # Алерт админу
    alert = (
        f"📥 *Новая заявка #{order_id}*\n\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 `{user.id}`\n"
        f"💼 Услуга: {service}\n"
        f"📝 {details[:300]}\n"
        f"📬 Контакт: {contact}"
    )
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ В работе", callback_data=f"order:working:{order_id}"),
                InlineKeyboardButton("❌ Закрыть", callback_data=f"order:closed:{order_id}"),
            ]])
            await context.bot.send_message(admin_id, alert, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            log.warning(f"Admin alert failed for {admin_id}: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=kb_main())
    return ConversationHandler.END


# ── Admin: обработка статуса заявки ─────────────────────────────────────────

async def handle_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    log.info(f"[order_action] from={query.from_user.id} data={query.data}")
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("Нет доступа")
        return
    await query.answer()
    try:
        _, status, order_id = query.data.split(":")
        order_id = int(order_id)
        update_order_status(order_id, status)
        label = "✅ В работе" if status == "working" else "❌ Закрыто"
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(label, callback_data="noop")
        ]]))
    except Exception as e:
        log.error(f"[order_action] error: {e}")


# ── Калькулятор ──────────────────────────────────────────────────────────────

async def handle_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    # calc:bot или calc:site — первый выбор
    if len(parts) == 2 and parts[1] in ("bot", "site"):
        calc_type = parts[1]
        context.user_data["calc_type"] = calc_type
        context.user_data["calc_chosen"] = set()
        await _show_calc_features(query, context, calc_type)
        return

    # calc:toggle:feature_id
    if parts[1] == "toggle":
        feature_id = parts[2]
        calc_type = context.user_data.get("calc_type", "bot")
        chosen: set = context.user_data.get("calc_chosen", set())
        if feature_id in chosen:
            chosen.discard(feature_id)
        else:
            chosen.add(feature_id)
        context.user_data["calc_chosen"] = chosen
        await _show_calc_features(query, context, calc_type)
        return

    # calc:result
    if parts[1] == "result":
        calc_type = context.user_data.get("calc_type", "bot")
        chosen: set = context.user_data.get("calc_chosen", set())
        data = CALC_FACTORS.get(calc_type, {})
        base = data.get("base", 5000)
        features = data.get("features", {})
        total = base
        lines = [f"Базовая стоимость: {base:,} ₽"]
        for fid, (fname, fprice) in features.items():
            if fid in chosen:
                total += fprice
                lines.append(f"+ {fname}: {fprice:,} ₽")
        lines.append(f"\n💰 *Итого: ~{total:,} ₽*")
        lines.append("\n_Цена ориентировочная. Точная — после обсуждения._")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Оставить заявку", callback_data="menu:order")],
            [InlineKeyboardButton("◀️ Пересчитать", callback_data=f"calc:{calc_type}")],
            [InlineKeyboardButton("🏠 Меню", callback_data="menu:main")],
        ])
        try:
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def _show_calc_features(query, context, calc_type: str):
    data = CALC_FACTORS.get(calc_type, {})
    features = data.get("features", {})
    chosen: set = context.user_data.get("calc_chosen", set())
    base = data.get("base", 5000)
    type_name = "Телеграм-бот" if calc_type == "bot" else "Сайт"

    buttons = []
    for fid, (fname, fprice) in features.items():
        mark = "✅ " if fid in chosen else "☐ "
        buttons.append([InlineKeyboardButton(
            f"{mark}{fname} (+{fprice:,} ₽)",
            callback_data=f"calc:toggle:{fid}"
        )])
    buttons.append([
        InlineKeyboardButton("🧮 Посчитать", callback_data="calc:result"),
        InlineKeyboardButton("◀️ Назад", callback_data="menu:calc"),
    ])

    total_now = base + sum(
        CALC_FACTORS[calc_type]["features"][fid][1]
        for fid in chosen
        if fid in CALC_FACTORS.get(calc_type, {}).get("features", {})
    )

    try:
        await query.edit_message_text(
            f"🧮 *Калькулятор — {type_name}*\n\n"
            f"База: {base:,} ₽\n"
            f"Выбери дополнительные функции:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception:
        pass


# ── register commands ─────────────────────────────────────────────────────────

async def post_init(app: Application):
    public = [
        BotCommand("start", "🏠 Главное меню"),
        BotCommand("menu", "📋 Открыть меню"),
    ]
    admin = public + [
        BotCommand("orders", "📥 Входящие заявки"),
    ]
    try:
        await app.bot.set_my_commands(public, scope=BotCommandScopeDefault())
    except Exception as e:
        log.warning(f"set_my_commands default: {e}")
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(admin, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            log.warning(f"set_my_commands admin {admin_id}: {e}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Заявка: ConversationHandler
    order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(svc_selected, pattern=r"^svc:")],
        states={
            ORDER_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_details)],
            ORDER_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_contact)],
        },
        fallbacks=[CommandHandler("cancel", order_cancel)],
        per_message=False,
        per_chat=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("orders", cmd_orders))
    # order action до conv — иначе ConversationHandler перехватит
    app.add_handler(CallbackQueryHandler(handle_order_action, pattern=r"^order:(working|closed):"))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(handle_calc, pattern=r"^calc:"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))
    app.add_handler(order_conv)

    log.info("LotOS bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
