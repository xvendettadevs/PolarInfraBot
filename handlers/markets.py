import json
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.database import db
from services.api import poly_api

router = Router()

class MarketStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_side = State()
    waiting_for_price = State()
    waiting_for_condition = State()
    waiting_for_edit_price = State()

@router.callback_query(F.data == "menu_markets")
async def market_menu(callback: types.CallbackQuery):
    watchlist = await db.get_user_watchlist(callback.from_user.id)
    
    if not watchlist:
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Paste Link", callback_data="menu_add_link")
        kb.button(text="🔙 Back", callback_data="back_home")
        kb.adjust(1)
        
        await callback.message.edit_text(
            "📈 <b>Market Watch</b>\n\n"
            "You are not tracking any markets yet.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        await list_alerts_handler(callback)

@router.callback_query(F.data == "menu_add_link")
async def add_link_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔗 Send me the Polymarket Event URL.")
    await state.set_state(MarketStates.waiting_for_url)
    await callback.answer()

@router.message(MarketStates.waiting_for_url)
async def process_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    markets = await poly_api.get_markets_by_url(url)
    
    if not markets:
        await message.answer("❌ No markets found.")
        return

    kb = InlineKeyboardBuilder()
    for m in markets[:10]:
        q_text = m.get('question', 'Unknown Market')
        if len(q_text) > 40:
            q_text = q_text[:37] + "..."
        m_id = m.get('id')
        kb.button(text=q_text, callback_data=f"sel_mkt:{m_id}")
    
    kb.adjust(1)
    await message.answer("👇 Select a market:", reply_markup=kb.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("sel_mkt:"))
async def select_market_handler(callback: types.CallbackQuery, state: FSMContext):
    market_id = callback.data.split(":")[1]
    await state.update_data(market_id=market_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🟩 Track YES", callback_data="side:YES")
    kb.button(text="🟥 Track NO", callback_data="side:NO")
    kb.adjust(2)
    
    await callback.message.answer("⚖️ Which outcome do you want to track?", reply_markup=kb.as_markup())
    await state.set_state(MarketStates.waiting_for_side)
    await callback.answer()

@router.callback_query(F.data.startswith("side:"), MarketStates.waiting_for_side)
async def select_side_handler(callback: types.CallbackQuery, state: FSMContext):
    side = callback.data.split(":")[1]
    await state.update_data(outcome=side)
    
    await callback.message.answer(
        f"Selected: <b>{side}</b>\n\n"
        "🔢 Enter target price (cents).\n"
        "Example: <b>50</b> for 50¢."
    )
    await state.set_state(MarketStates.waiting_for_price)
    await callback.answer()

@router.message(MarketStates.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        raw_input = float(message.text.replace(',', '.'))
        if raw_input > 1 and raw_input <= 100:
            price = raw_input / 100.0
        else:
            price = raw_input

        if not (0 < price <= 1):
            await message.answer("❌ Price must be between 0 and 100.")
            return

        await state.update_data(price=price)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="📈 Goes ABOVE", callback_data="cond:ABOVE")
        kb.button(text="📉 Goes BELOW", callback_data="cond:BELOW")
        kb.adjust(2)
        
        cents_display = f"{price*100:.1f}"
        await message.answer(
            f"🎯 Target: <b>{cents_display}¢</b>\n"
            "Alert when price goes...", 
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(MarketStates.waiting_for_condition)
        
    except ValueError:
        await message.answer("❌ Invalid number.")

@router.callback_query(F.data.startswith("cond:"), MarketStates.waiting_for_condition)
async def condition_handler(callback: types.CallbackQuery, state: FSMContext):
    condition = callback.data.split(":")[1]
    data = await state.get_data()
    
    market_id = data['market_id']
    price = data['price']
    outcome = data['outcome']

    market_info = await poly_api.get_market_data(market_id)
    market_name = market_info.get('question') if market_info else f"Market {market_id}"
    
    await db.add_to_watchlist(
        callback.from_user.id, 
        market_id, 
        market_name, 
        price, 
        condition,
        outcome
    )
    
    cents_display = f"{price*100:.1f}"
    emoji = "🟩" if outcome == "YES" else "🟥"
    arrow = "📈" if condition == "ABOVE" else "📉"
    
    await callback.message.answer(
        f"✅ <b>Alert Saved!</b>\n"
        f"Market: {market_name}\n"
        f"{emoji} {outcome} {arrow} {cents_display}¢",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("menu_my_alerts"))
@router.callback_query(F.data.startswith("list_alerts:"))
async def list_alerts_handler(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
    except:
        page = 0
        
    alerts = await db.get_user_watchlist(callback.from_user.id)
    
    if not alerts:
        await market_menu(callback)
        return

    limit = 6
    start = page * limit
    end = start + limit
    page_items = alerts[start:end]

    kb = InlineKeyboardBuilder()
    for a in page_items:
        slug_clean = a['market_slug'].replace('-', ' ')
        if len(slug_clean) > 20:
            slug_clean = slug_clean[:18] + ".."
            
        icon = "📈" if a['condition'] == 'ABOVE' else "📉"
        outcome_emoji = "🟩" if a['outcome'] == 'YES' else "🟥"
        price_fmt = f"{a['alert_price']*100:.0f}¢"
        
        text = f"{outcome_emoji} {slug_clean} {icon} {price_fmt}"
        kb.button(text=text, callback_data=f"view_a:{a['id']}")
    
    kb.adjust(1)
    
    row_btns = []
    if page > 0:
        row_btns.append(types.InlineKeyboardButton(text="⬅️ Prev", callback_data=f"list_alerts:{page-1}"))
    if end < len(alerts):
        row_btns.append(types.InlineKeyboardButton(text="Next ➡️", callback_data=f"list_alerts:{page+1}"))
    
    kb.row(*row_btns)
    
    kb.row(
        types.InlineKeyboardButton(text="➕ Add Another", callback_data="menu_add_link"),
        types.InlineKeyboardButton(text="🔙 Back", callback_data="back_home")
    )

    await callback.message.edit_text(
        f"🔔 <b>Your Alerts</b> (Page {page+1})",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("view_a:"))
async def view_alert_handler(callback: types.CallbackQuery):
    a_id = int(callback.data.split(":")[1])
    alert = await db.get_alert_by_id(a_id)
    
    if not alert:
        await callback.answer("Alert not found", show_alert=True)
        await list_alerts_handler(callback) 
        return

    current_price_str = "⏳..."
    try:
        m_data = await poly_api.get_market_data(alert['market_id'])
        if m_data:
            outcomes = m_data.get('outcomePrices', [])
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            
            if outcomes:
                p_yes = float(outcomes[0])
                if alert['outcome'] == 'YES':
                    curr = p_yes
                else:
                    curr = float(outcomes[1]) if len(outcomes) > 1 else (1.0 - p_yes)
                current_price_str = f"{curr*100:.1f}¢"
    except Exception:
        current_price_str = "⚠️ Error"

    market_name = alert['market_slug'].replace('-', ' ')
    cond_arrow = "📈" if alert['condition'] == "ABOVE" else "📉"
    price_fmt = f"{alert['alert_price']*100:.1f}¢"
    outcome = alert['outcome']
    outcome_emoji = "🟩" if outcome == "YES" else "🟥"
    
    text = (
        f"🔔 <b>Alert Settings</b>\n\n"
        f"📜 <b>Market:</b> {market_name}\n"
        f"🎲 <b>Outcome:</b> {outcome_emoji} {outcome}\n"
        f"💲 <b>Current:</b> {current_price_str}\n"
        f"🎯 <b>Target:</b> {price_fmt}\n"
        f"⚖️ <b>Condition:</b> {alert['condition']} {cond_arrow}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Edit Price", callback_data=f"edit_a_price:{a_id}")
    kb.button(text="🔄 Switch Above/Below", callback_data=f"tog_a_cond:{a_id}")
    kb.button(text="🔄 Switch Yes/No", callback_data=f"tog_a_out:{a_id}")
    kb.button(text="🗑 Delete Alert", callback_data=f"del_a:{a_id}")
    kb.button(text="🔙 Back to List", callback_data="list_alerts:0")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("tog_a_cond:"))
async def toggle_alert_condition(callback: types.CallbackQuery):
    a_id = int(callback.data.split(":")[1])
    alert = await db.get_alert_by_id(a_id)
    if not alert: return

    new_cond = "BELOW" if alert['condition'] == "ABOVE" else "ABOVE"
    await db.update_alert(a_id, alert['alert_price'], new_cond, alert['outcome'])
    await view_alert_handler(callback)

@router.callback_query(F.data.startswith("tog_a_out:"))
async def toggle_alert_outcome(callback: types.CallbackQuery):
    a_id = int(callback.data.split(":")[1])
    alert = await db.get_alert_by_id(a_id)
    if not alert: return

    new_out = "NO" if alert['outcome'] == "YES" else "YES"
    await db.update_alert(a_id, alert['alert_price'], alert['condition'], new_out)
    await view_alert_handler(callback)

@router.callback_query(F.data.startswith("edit_a_price:"))
async def edit_alert_price_start(callback: types.CallbackQuery, state: FSMContext):
    a_id = int(callback.data.split(":")[1])
    await state.update_data(editing_alert_id=a_id)
    
    await callback.message.answer(
        "⌨️ Enter new target price in cents (e.g. <b>55</b> for 55¢):", 
        parse_mode="HTML"
    )
    await state.set_state(MarketStates.waiting_for_edit_price)
    await callback.answer()

@router.message(MarketStates.waiting_for_edit_price)
async def process_edit_price(message: types.Message, state: FSMContext):
    try:
        raw_input = float(message.text.replace(',', '.'))
        if raw_input > 1 and raw_input <= 100:
            new_price = raw_input / 100.0
        else:
            new_price = raw_input

        if not (0 < new_price <= 1):
            await message.answer("❌ Price must be between 0 and 100.")
            return

        data = await state.get_data()
        a_id = data['editing_alert_id']
        
        alert = await db.get_alert_by_id(a_id)
        if alert:
            await db.update_alert(a_id, new_price, alert['condition'], alert['outcome'])
            
            kb = InlineKeyboardBuilder()
            kb.button(text="🔙 Back to Alert", callback_data=f"view_a:{a_id}")
            
            await message.answer(
                f"✅ Price updated to <b>{new_price*100:.1f}¢</b>", 
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Invalid number.")

@router.callback_query(F.data.startswith("del_a:"))
async def delete_alert_handler(callback: types.CallbackQuery):
    a_id = int(callback.data.split(":")[1])
    await db.delete_alert(a_id, callback.from_user.id)
    await callback.answer("🗑 Alert deleted")
    await list_alerts_handler(callback)