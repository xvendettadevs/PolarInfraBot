import json
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.database import db
from services.api import poly_api

router = Router()

class WalletStates(StatesGroup):
    waiting_for_address = State()
    waiting_for_alias = State()
    waiting_for_min_vol = State()
    waiting_for_price_val = State()

@router.callback_query(F.data == "menu_wallets")
async def wallets_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Add Wallet", callback_data="add_wallet_start")
    kb.button(text="📋 My Wallets", callback_data="list_wallets:0")
    kb.button(text="🔙 Back", callback_data="back_home")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "👛 <b>Wallet Tracker</b>\n\n"
        "Manage your tracked wallets here.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "add_wallet_start")
async def add_wallet_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 Send the Polygon wallet address (0x...).")
    await state.set_state(WalletStates.waiting_for_address)
    await callback.answer()

@router.message(WalletStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    if not address.startswith("0x") or len(address) != 42:
        await message.answer("❌ Invalid address format.")
        return

    await state.update_data(address=address)
    await message.answer("🏷 Enter a name (alias) for this wallet.")
    await state.set_state(WalletStates.waiting_for_alias)

@router.message(WalletStates.waiting_for_alias)
async def process_alias(message: types.Message, state: FSMContext):
    alias = message.text.strip()
    data = await state.get_data()
    address = data['address']

    await db.add_wallet(message.from_user.id, address, alias)
    await message.answer(f"✅ Wallet <b>{alias}</b> added!", parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data.startswith("list_wallets:"))
async def list_wallets_handler(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
    except:
        page = 0
        
    wallets = await db.get_user_wallets(callback.from_user.id)
    
    if not wallets:
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Add Wallet", callback_data="add_wallet_start")
        kb.button(text="🔙 Back", callback_data="menu_wallets")
        kb.adjust(1)
        await callback.message.edit_text("📭 You have no tracked wallets.", reply_markup=kb.as_markup())
        return

    limit = 10
    start = page * limit
    end = start + limit
    page_items = wallets[start:end]

    kb = InlineKeyboardBuilder()
    for w in page_items:
        addr_short = f"{w['wallet_address'][:6]}...{w['wallet_address'][-4:]}"
        kb.button(text=f"👤 {w['alias']} ({addr_short})", callback_data=f"view_w:{w['id']}")
    
    kb.adjust(1)
    
    row_btns = []
    if page > 0:
        row_btns.append(types.InlineKeyboardButton(text="⬅️ Prev", callback_data=f"list_wallets:{page-1}"))
    if end < len(wallets):
        row_btns.append(types.InlineKeyboardButton(text="Next ➡️", callback_data=f"list_wallets:{page+1}"))
    
    kb.row(*row_btns)
    kb.row(types.InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallets"))

    await callback.message.edit_text(
        f"📋 <b>Your Wallets</b> (Page {page+1})",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("view_w:"))
async def view_wallet_handler(callback: types.CallbackQuery):
    w_id = int(callback.data.split(":")[1])
    wallets = await db.get_user_wallets(callback.from_user.id)
    wallet = next((w for w in wallets if w['id'] == w_id), None)
    
    if not wallet:
        await callback.answer("Wallet not found", show_alert=True)
        return

    positions = await poly_api.get_wallet_positions(wallet['wallet_address'])
    
    text = f"👤 <b>{wallet['alias']}</b>\n"
    text += f"<code>{wallet['wallet_address']}</code>\n\n"
    text += f"⚙️ <b>Settings:</b>\n"
    text += f"• Min Volume: ${wallet['min_vol']:.0f}\n"
    text += f"• Price Cond: {wallet['price_cond']} {wallet['price_target']}\n"
    text += f"• New Markets Only: {'Yes' if wallet['notify_new_markets'] else 'No'}\n\n"
    
    if positions:
        text += "📊 <b>Top Positions (by Value):</b>\n"
        for p in positions[:8]:
            title = p.get('title')
            if not title and 'market' in p:
                title = p['market'].get('question')
            if not title:
                title = "Unknown Market"
                
            outcome = p.get('outcome', p.get('side', '?'))
            size = float(p.get('size', 0))
            value = float(p.get('currentValue', 0))
            
            text += f"• {title[:35]}...\n"
            text += f"  {outcome} | {size:.0f} sh | <b>${value:.2f}</b>\n\n"
    else:
        text += "📭 No active positions found."

    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Settings", callback_data=f"set_w:{w_id}")
    kb.button(text="🗑 Delete Wallet", callback_data=f"del_w:{w_id}")
    kb.button(text="🔙 Back", callback_data="list_wallets:0")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("set_w:"))
async def settings_wallet_handler(callback: types.CallbackQuery):
    w_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(w_id)
    
    if not wallet:
        await callback.answer("Wallet not found")
        return
        
    nm_status = "✅" if wallet['notify_new_markets'] else "❌"
    
    text = f"⚙️ <b>Settings for {wallet['alias']}</b>\n\n"
    text += f"💰 Min Volume: ${wallet['min_vol']}\n"
    text += f"📈 Price Filter: {wallet['price_cond']} {wallet['price_target']}\n"
    text += f"🆕 New Markets Only: {nm_status}"

    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Set Min Volume", callback_data=f"set_vol:{w_id}")
    kb.button(text="🎯 Set Price Filter", callback_data=f"set_price:{w_id}")
    kb.button(text="🔄 Toggle 'New Markets Only'", callback_data=f"tog_nm:{w_id}")
    kb.button(text="🔙 Back", callback_data=f"view_w:{w_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("tog_nm:"))
async def toggle_new_markets(callback: types.CallbackQuery):
    w_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(w_id)
    new_val = 0 if wallet['notify_new_markets'] else 1
    
    await db.update_wallet_settings(
        w_id, wallet['min_vol'], wallet['price_target'], 
        wallet['price_cond'], new_val
    )
    await settings_wallet_handler(callback)

@router.callback_query(F.data.startswith("set_vol:"))
async def set_vol_start(callback: types.CallbackQuery, state: FSMContext):
    w_id = int(callback.data.split(":")[1])
    await state.update_data(w_id=w_id)
    await callback.message.answer("⌨️ Enter minimum trade amount in USD (e.g., 500):")
    await state.set_state(WalletStates.waiting_for_min_vol)
    await callback.answer()

@router.message(WalletStates.waiting_for_min_vol)
async def process_min_vol(message: types.Message, state: FSMContext):
    try:
        vol = float(message.text.strip())
        data = await state.get_data()
        w_id = data['w_id']
        wallet = await db.get_wallet_by_id(w_id)
        
        await db.update_wallet_settings(
            w_id, vol, wallet['price_target'], 
            wallet['price_cond'], wallet['notify_new_markets']
        )
        await message.answer("✅ Minimum volume updated.")
        await state.clear()
    except ValueError:
        await message.answer("❌ Invalid number.")

@router.callback_query(F.data.startswith("set_price:"))
async def set_price_start(callback: types.CallbackQuery, state: FSMContext):
    w_id = int(callback.data.split(":")[1])
    await state.update_data(w_id=w_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Above (>)", callback_data="price_cond:ABOVE")
    kb.button(text="Below (<)", callback_data="price_cond:BELOW")
    kb.button(text="Disable", callback_data="price_cond:NONE")
    kb.adjust(2)
    
    await callback.message.answer("Choose price condition:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("price_cond:"))
async def process_price_cond(callback: types.CallbackQuery, state: FSMContext):
    cond = callback.data.split(":")[1]
    data = await state.get_data()
    w_id = data['w_id']
    
    if cond == "NONE":
        wallet = await db.get_wallet_by_id(w_id)
        await db.update_wallet_settings(
            w_id, wallet['min_vol'], 0, "NONE", wallet['notify_new_markets']
        )
        await callback.message.answer("✅ Price filter disabled.")
        await state.clear()
        return

    await state.update_data(cond=cond)
    await callback.message.answer(f"⌨️ Enter price threshold (0.01 - 0.99) for {cond}:")
    await state.set_state(WalletStates.waiting_for_price_val)
    await callback.answer()

@router.message(WalletStates.waiting_for_price_val)
async def process_price_val(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.strip())
        if not (0 < val < 1):
            await message.answer("❌ Price must be between 0 and 1.")
            return

        data = await state.get_data()
        w_id = data['w_id']
        cond = data['cond']
        wallet = await db.get_wallet_by_id(w_id)
        
        await db.update_wallet_settings(
            w_id, wallet['min_vol'], val, cond, wallet['notify_new_markets']
        )
        await message.answer(f"✅ Price filter set: {cond} {val}")
        await state.clear()
    except ValueError:
        await message.answer("❌ Invalid number.")

@router.callback_query(F.data.startswith("del_w:"))
async def delete_wallet_handler(callback: types.CallbackQuery):
    w_id = int(callback.data.split(":")[1])
    success = await db.delete_wallet(w_id, callback.from_user.id)
    
    if success:
        await callback.answer("✅ Wallet deleted")
        await list_wallets_handler(callback)
    else:
        await callback.answer("❌ Error deleting wallet", show_alert=True)