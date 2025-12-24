from aiogram import Router, types, F, Bot   
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database.database import db
from services.api import poly_api
from aiogram.types import FSInputFile

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    await db.add_user(message.from_user.id, message.from_user.username)
    
    rkb = ReplyKeyboardBuilder()
    rkb.button(text="📚 Guide")
    rkb.button(text="❓ FAQ")
    rkb.button(text="📰 Feedback")
    rkb.button(text="🛠 Settings")
    rkb.button(text="Polar Pro")
    rkb.adjust(2, 2, 1)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Track Markets", callback_data="menu_markets")
    kb.button(text="🔔 My Alerts", callback_data="menu_my_alerts")
    kb.button(text="👛 Track Wallets", callback_data="menu_wallets")
    kb.button(text="🤖 Arb Alerts", callback_data="menu_arb")
    kb.adjust(2)
    photo_path = "handlers/main.jpg"
    photo_file = FSInputFile(photo_path)

    await bot.send_photo(chat_id=message.from_user.id, photo=photo_file, caption=
        f"Hello, {message.from_user.first_name}!\n"
        "Welcome to <b>PolarTerminal</b>\n\n"
        "Your advanced toolkit for Polymarket analytics and alerts.",
        reply_markup=rkb.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )
    await message.answer("Choose an action:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_home")
async def back_home_handler(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Track Markets", callback_data="menu_markets")
    kb.button(text="🔔 My Alerts", callback_data="menu_my_alerts")
    kb.button(text="👛 Track Wallets", callback_data="menu_wallets")
    kb.button(text="🤖 Arb Alerts", callback_data="menu_arb")
    kb.adjust(2)
    
    await callback.message.edit_text("Main Menu:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "menu_arb")
async def arb_menu_handler(callback: types.CallbackQuery):
    user_settings = await db.get_user_settings(callback.from_user.id)
    status = "✅ ON" if user_settings['arb_alerts'] else "❌ OFF"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Toggle Alerts: {status}", callback_data="toggle_arb")
    kb.button(text="🔄 Scan Now", callback_data="scan_arb_now")
    kb.button(text="🔙 Back", callback_data="back_home")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"🤖 <b>Arbitrage Alerts</b>\n\n"
        f"Status: {status}\n\n"
        "Receive real-time notifications when a risk-free arbitrage opportunity (>1.5%) is detected.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "toggle_arb")
async def toggle_arb_handler(callback: types.CallbackQuery):
    new_val = await db.toggle_arb_alerts(callback.from_user.id)
    status = "✅ ON" if new_val else "❌ OFF"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Toggle Alerts: {status}", callback_data="toggle_arb")
    kb.button(text="🔄 Scan Now", callback_data="scan_arb_now")
    kb.button(text="🔙 Back", callback_data="back_home")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"🤖 <b>Arbitrage Alerts</b>\n\n"
        f"Status: {status}\n\n"
        "Receive real-time notifications when a risk-free arbitrage opportunity (>1.5%) is detected.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "scan_arb_now")
async def scan_arb_now_handler(callback: types.CallbackQuery):
    await callback.message.edit_text("🔎 Scanning markets...")
    opps = await poly_api.check_arbitrage()
    
    if opps and len(opps) > 0:
        best = opps[0]
        text = (
            f"💎 <b>Best Opportunity Found</b>\n\n"
            f"❓ {best['question']}\n"
            f"📈 Profit: <b>{best['profit_str']}</b>\n"
            f"🟩 YES: {best['yes']} | 🟥 NO: {best['no']}\n\n"
            f"🔗 <a href='{best['url']}'>Open Market</a>"
        )
    else:
        text = "✅ No significant arbitrage opportunities found right now."
        
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back", callback_data="menu_arb")
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), disable_web_page_preview=True, parse_mode="HTML")

@router.message(F.text == "Polar Pro")
async def polar_pro_handler(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Visit Website", url="https://polarterminal.pro")
    
    await message.answer(
        "🚀 <b>Polar Pro</b>\n\n"
        "Unlock the full potential of Polymarket analytics with our web terminal.\n\n"
        "• Advanced Charting\n"
        "• Real-time Order Books\n"
        "• Whale Watching Dashboard\n"
        "• API Access",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.message(F.text == "📚 Guide")
async def guide_handler(message: types.Message):
    text = (
        "📚 <b>User Guide</b>\n\n"
        "<b>1. Price Alerts</b>\n"
        "Click 'Track Markets' and paste a Polymarket event link. Set a target price (e.g., 60 cents) and condition (Above/Below). The bot will DM you when the price hits.\n\n"
        "<b>2. Wallet Tracker</b>\n"
        "Monitor whales or smart money. Add a wallet address, set a minimum volume filter (e.g., $1000), and receive alerts on every trade.\n\n"
        "<b>3. Arbitrage Alerts</b>\n"
        "Enable Arb Alerts to get notified when the YES + NO shares of a market sum to less than $1.00, guaranteeing a profit."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📰 Feedback")
async def feedback_handler(message: types.Message):
    text = (
        "📰 <b>Feedback & Support</b>\n\n"
        "Have a suggestion or found a bug? We'd love to hear from you.\n\n"
        "📧 Email us at: <code>support@polarterminal.pro</code>"
    )
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🛠 Settings")
async def settings_handler(message: types.Message):
    user_settings = await db.get_user_settings(message.from_user.id)
    
    mkt_status = "✅ ON" if user_settings['alert_markets'] else "❌ OFF"
    evt_status = "✅ ON" if user_settings['alert_events'] else "❌ OFF"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📢 New Markets: {mkt_status}", callback_data="tog_mkt")
    kb.button(text=f"🗓 New Events: {evt_status}", callback_data="tog_evt")
    kb.button(text="📜 Changelog", callback_data="view_changelog")
    kb.button(text="🔙 Back", callback_data="back_home_settings")
    kb.adjust(1)
    
    await message.answer(
        "🛠 <b>Global Settings</b>\n\n"
        "<b>Markets:</b> Individual betting contracts (can be spammy).\n"
        "<b>Events:</b> Grouped events (recommended).",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_home_settings")
async def back_home_handler(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Track Markets", callback_data="menu_markets")
    kb.button(text="🔔 My Alerts", callback_data="menu_my_alerts")
    kb.button(text="👛 Track Wallets", callback_data="menu_wallets")
    kb.button(text="🤖 Arb Alerts", callback_data="menu_arb")
    kb.adjust(2)
    
    await callback.message.edit_text("Main Menu:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "tog_mkt")
async def toggle_markets_handler(callback: types.CallbackQuery):
    new_val = await db.toggle_market_alerts(callback.from_user.id)
    
    user_settings = await db.get_user_settings(callback.from_user.id)
    mkt_status = "✅ ON" if user_settings['alert_markets'] else "❌ OFF"
    evt_status = "✅ ON" if user_settings['alert_events'] else "❌ OFF"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📢 New Markets: {mkt_status}", callback_data="tog_mkt")
    kb.button(text=f"🗓 New Events: {evt_status}", callback_data="tog_evt")
    kb.button(text="📜 Changelog", callback_data="view_changelog")
    kb.button(text="🔙 Back", callback_data="back_home_settings")
    kb.adjust(1)
    
    await callback.message.edit_text("🛠 <b>Global Settings</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "tog_evt")
async def toggle_events_handler(callback: types.CallbackQuery):
    new_val = await db.toggle_event_alerts(callback.from_user.id)
    
    user_settings = await db.get_user_settings(callback.from_user.id)
    mkt_status = "✅ ON" if user_settings['alert_markets'] else "❌ OFF"
    evt_status = "✅ ON" if user_settings['alert_events'] else "❌ OFF"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📢 New Markets: {mkt_status}", callback_data="tog_mkt")
    kb.button(text=f"🗓 New Events: {evt_status}", callback_data="tog_evt")
    kb.button(text="📜 Changelog", callback_data="view_changelog")
    kb.button(text="🔙 Back", callback_data="back_home_settings")
    kb.adjust(1)
    
    await callback.message.edit_text("🛠 <b>Global Settings</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "view_changelog")
async def changelog_handler(callback: types.CallbackQuery):
    text = (
        "📜 <b>Changelog</b>\n\n"
        "<b>v2.3</b>\n"
        "- Separated Market and Event alerts\n"
        "- Added Volume & Liquidity data\n"
        "- Improved date handling\n\n"
        "<b>v2.2</b>\n"
        "- Added Global New Market & Event Alerts\n"
        "- Improved Arbitrage Scanner"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back", callback_data="back_home_settings")
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.message(F.text == "❓ FAQ")
async def faq_handler(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="How does Arbitrage work?", callback_data="faq:arb")
    kb.button(text="Are alerts real-time?", callback_data="faq:realtime")
    kb.button(text="What is Min Volume?", callback_data="faq:minvol")
    kb.button(text="Is this free?", callback_data="faq:free")
    kb.adjust(1)
    
    await message.answer("❓ <b>Frequently Asked Questions</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("faq:"))
async def faq_detail_handler(callback: types.CallbackQuery):
    topic = callback.data.split(":")[1]
    
    answers = {
        "arb": "<b>Arbitrage:</b>\nSometimes the combined price of YES and NO shares is less than $1.00 (e.g., 0.45 + 0.50 = 0.95). Buying both guarantees a payout of $1.00, resulting in instant profit.",
        "realtime": "<b>Latency:</b>\nWe scan markets every 30-60 seconds. While highly responsive, it is not millisecond-level HFT speed. It is designed for retail traders.",
        "minvol": "<b>Minimum Volume:</b>\nIn Wallet Tracking, this filters out small trades. If set to $1000, you will only receive alerts for trades larger than $1000.",
        "free": "<b>Pricing:</b>\nPolarTerminal is currently free to use while in beta. Pro features will be introduced later."
    }
    
    text = answers.get(topic, "Unknown topic.")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back to FAQ", callback_data="back_faq")
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "back_faq")
async def back_faq_handler(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="How does Arbitrage work?", callback_data="faq:arb")
    kb.button(text="Are alerts real-time?", callback_data="faq:realtime")
    kb.button(text="What is Min Volume?", callback_data="faq:minvol")
    kb.button(text="Is this free?", callback_data="faq:free")
    kb.adjust(1)
    
    await callback.message.edit_text("❓ <b>Frequently Asked Questions</b>", reply_markup=kb.as_markup(), parse_mode="HTML")