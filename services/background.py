import asyncio
import logging
import json
import time
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.database import db
from services.api import poly_api

logger = logging.getLogger(__name__)

async def start_background_tasks(bot: Bot):
    asyncio.create_task(watch_prices(bot))
    asyncio.create_task(track_wallets(bot))
    asyncio.create_task(scanner_arbitrage(bot))
    asyncio.create_task(scanner_new_markets(bot))

async def watch_prices(bot: Bot):
    while True:
        try:
            alerts = await db.get_all_watchlists()
            for alert in alerts:
                market_data = await poly_api.get_market_data(alert['market_id'])
                if not market_data: continue

                try:
                    outcome_prices = market_data.get('outcomePrices', [])
                    if isinstance(outcome_prices, str):
                        outcome_prices = json.loads(outcome_prices)
                    
                    if not outcome_prices: continue
                        
                    yes_price = float(outcome_prices[0])
                    outcome_target = alert['outcome']
                    
                    if outcome_target == 'NO':
                        if len(outcome_prices) > 1:
                            current_price = float(outcome_prices[1])
                        else:
                            current_price = 1.0 - yes_price
                    else:
                        current_price = yes_price

                except Exception:
                    continue
                
                trigger = False
                if alert['condition'] == 'ABOVE' and current_price >= alert['alert_price']:
                    trigger = True
                elif alert['condition'] == 'BELOW' and current_price <= alert['alert_price']:
                    trigger = True
                
                if trigger:
                    curr_cents = f"{current_price*100:.1f}"
                    targ_cents = f"{alert['alert_price']*100:.1f}"
                    emoji = "🟩" if outcome_target == "YES" else "🟥"
                    arrow = "📈" if alert['condition'] == "ABOVE" else "📉"
                    
                    market_name = market_data.get('question', alert['market_slug'])
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔗 View Market", url=f"https://polymarket.com/market/{alert['market_slug']}")
                    ]])

                    try:
                        await bot.send_message(
                            alert['user_id'],
                            f"🚨 <b>Price Alert!</b>\n\n"
                            f"📊 {market_name}\n"
                            f"{emoji} <b>{outcome_target}</b> Price: <b>{curr_cents}¢</b>\n"
                            f"🎯 Target: {targ_cents}¢ ({arrow})",
                            reply_markup=kb
                        )
                        await db.delete_alert(alert['id'], alert['user_id'])
                    except Exception as e:
                        logger.error(f"Failed to send alert: {e}")

        except Exception as e:
            logger.error(f"Price Watch Error: {e}")
        
        await asyncio.sleep(60)

async def track_wallets(bot: Bot):
    logger.info("Starting Wallet Tracker...")
    while True:
        try:
            wallets = await db.get_tracked_wallets()
            for w in wallets:
                trades = await poly_api.get_wallet_activity(w['wallet_address'])
                
                if not trades:
                    continue

                latest_trade = trades[0]
                trade_id = latest_trade['id']
                
                if w['last_tx_hash'] != trade_id:
                    await db.update_wallet_tx(w['id'], trade_id)
                    
                    if w['last_tx_hash'] is None:
                        continue

                    fpmm = latest_trade.get('fpmm', {})
                    market_id = fpmm.get('id')
                    market_slug = fpmm.get('slug', '')
                    title = fpmm.get('question', 'Unknown Market')
                    
                    amount_usd = float(latest_trade.get('transactionAmount', 0))
                    outcome_tokens = float(latest_trade.get('outcomeTokensTraded', 0))
                    
                    price_per_share = 0
                    if outcome_tokens > 0:
                        price_per_share = amount_usd / outcome_tokens

                    if amount_usd < w['min_vol']:
                        continue

                    if w['price_cond'] != 'NONE':
                        if w['price_cond'] == 'ABOVE' and price_per_share < w['price_target']:
                            continue
                        if w['price_cond'] == 'BELOW' and price_per_share > w['price_target']:
                            continue

                    seen_markets = json.loads(w['seen_markets']) if w['seen_markets'] else []
                    is_new_market = market_id not in seen_markets

                    if w['notify_new_markets'] and not is_new_market:
                        continue
                        
                    if is_new_market and market_id:
                        seen_markets.append(market_id)
                        await db.update_wallet_seen_markets(w['id'], seen_markets)

                    outcome_idx = latest_trade.get('outcomeIndex')
                    trade_type = latest_trade.get('type')
                    side = "YES" if outcome_idx == 0 else "NO"
                    
                    if trade_type == "Sell":
                        action_emoji = "🔴"
                        action_text = "SOLD"
                    else:
                        action_emoji = "🟢"
                        action_text = "BOUGHT"
                        
                    header = "🆕 <b>New Market Entry!</b>" if is_new_market else "⚡ <b>New Trade Detected!</b>"
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔗 View Market", url=f"https://polymarket.com/market/{market_slug}"),
                        InlineKeyboardButton(text="🔗 View TX", url=f"https://polygonscan.com/tx/{latest_trade['transactionHash']}")
                    ]])
                    
                    msg = (
                        f"🔭 <b>Wallet Tracker: {w['alias']}</b>\n\n"
                        f"{header}\n"
                        f"📜 {title}\n"
                        f"{action_emoji} {action_text} <b>{side}</b>\n"
                        f"💲 Price: {price_per_share:.3f}¢\n"
                        f"💰 Amount: ${amount_usd:.2f}"
                    )
                    
                    await bot.send_message(w['user_id'], msg, reply_markup=kb)
                
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Wallet Track Error: {e}")
        
        await asyncio.sleep(60)

async def scanner_arbitrage(bot: Bot):
    sent_arbs = set()
    last_clear = time.time()

    while True:
        try:
            if time.time() - last_clear > 300:
                sent_arbs.clear()
                last_clear = time.time()

            opps = await poly_api.check_arbitrage()
            users = await db.get_users_for_arb()
            
            if not users or not opps:
                await asyncio.sleep(60)
                continue

            for opp in opps:
                if opp['profit'] < 1.5: continue
                if opp['id'] in sent_arbs: continue
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔗 Open Market", url=opp['url'])
                ]])

                text = (
                    f"💎 <b>Arbitrage Opportunity!</b>\n\n"
                    f"❓ {opp['question']}\n"
                    f"📈 Profit: <b>{opp['profit_str']}</b>\n"
                    f"🟩 YES Price: {opp['yes']}\n"
                    f"🟥 NO Price: {opp['no']}"
                )

                for uid in users:
                    try:
                        await bot.send_message(uid, text, reply_markup=kb)
                    except:
                        pass
                
                sent_arbs.add(opp['id'])

        except Exception as e:
            logger.error(f"Arb Scanner Error: {e}")
            
        await asyncio.sleep(60)

async def scanner_new_markets(bot: Bot):
    seen_market_ids = set()
    seen_event_ids = set()
    first_run = True

    while True:
        try:
            logging.info("Scanning for new markets and events...")
            markets = await poly_api.get_recent_markets()
            events = await poly_api.get_recent_events()
            
            try:
                with open("last_scan_markets.json", "w", encoding="utf-8") as f:
                    json.dump(markets, f, indent=4, ensure_ascii=False)
                with open("last_scan_events.json", "w", encoding="utf-8") as f:
                    json.dump(events, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving scan files: {e}")

            users_mkt = await db.get_users_for_markets()
            users_evt = await db.get_users_for_events()
            
            current_m_ids = {str(m['id']) for m in markets}
            current_e_ids = {str(e['id']) for e in events}
            
            if first_run:
                seen_market_ids.update(current_m_ids)
                seen_event_ids.update(current_e_ids)
                first_run = False
                await asyncio.sleep(10)
                continue

            new_m_ids = current_m_ids - seen_market_ids
            new_e_ids = current_e_ids - seen_event_ids
            
            if users_mkt and new_m_ids:
                for m in markets:
                    m_id = str(m['id'])
                    if m_id in new_m_ids:
                        desc = m.get('description', '')
                        if desc and len(desc) > 200:
                            desc = desc[:200] + "..."
                        
                        start_date = m.get('startDate')
                        if start_date:
                            start_date = start_date.split('T')[0]
                        else:
                            start_date = m.get('createdAt', '').split('T')[0]

                        end_date = m.get('endDate', '').split('T')[0]

                        text = (
                            f"📣 <b>New Market Listed!</b>\n\n"
                            f"📜 <b>{m.get('question')}</b>\n\n"
                        )
                        
                        if desc:
                            text += f"ℹ️ <i>{desc}</i>\n\n"
                            
                        text += (
                            f"📅 Start: {start_date}\n"
                            f"🏁 End: {end_date}"
                        )
                        
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔗 View Market", url=f"https://polymarket.com/market/{m.get('slug')}")
                        ]])
                        
                        for uid in users_mkt:
                            try:
                                await bot.send_message(uid, text, reply_markup=kb)
                            except:
                                pass
            
            if users_evt and new_e_ids:
                for e in events:
                    e_id = str(e['id'])
                    if e_id in new_e_ids:
                        start_date = e.get('startDate')
                        if start_date:
                            start_date = start_date.split('T')[0]
                        else:
                            start_date = e.get('creationDate', '').split('T')[0]
                            if not start_date: start_date = "TBA"

                        end_date = e.get('endDate', '').split('T')[0]
                        
                        desc = e.get('description', '')
                        if desc and len(desc) > 150:
                            desc = desc[:150] + "..."

                        text = (
                            f"🗓 <b>New Event Listed!</b>\n\n"
                            f"📜 <b>{e.get('title')}</b>\n\n"
                        )
                        
                        if desc:
                            text += f"ℹ️ {desc}\n\n"
                            
                        text += (
                            f"📅 Start: {start_date}\n"
                            f"🏁 End: {end_date}"
                        )
                        
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔗 View Event", url=f"https://polymarket.com/event/{e.get('slug')}")
                        ]])
                        
                        for uid in users_evt:
                            try:
                                await bot.send_message(uid, text, reply_markup=kb)
                            except:
                                pass

            seen_market_ids.update(new_m_ids)
            seen_event_ids.update(new_e_ids)

        except Exception as e:
            logger.error(f"New Market/Event Scanner Error: {e}")
        
        await asyncio.sleep(60)