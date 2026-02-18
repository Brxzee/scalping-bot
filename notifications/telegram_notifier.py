"""
Telegram notifier for trading alerts.
Accepts both legacy setup dict (entry, stop_loss, take_profit, etc.) and
SetupRecord from engine (via setup_to_telegram_dict).
"""
import asyncio
from typing import Dict, List, Any

from loguru import logger
from telegram import Bot
from telegram.error import TelegramError


class TelegramNotifier:
    """Send trading alerts via Telegram."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_message(self, message: str, parse_mode: str = "HTML"):
        """Send a message to Telegram."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
            )
            logger.info("Telegram message sent successfully")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_setup_alert(self, setup: Dict[str, Any]):
        """
        Send a formatted setup alert.
        setup may be the legacy format (entry, stop_loss, take_profit, key_level, etc.)
        or already in that format from engine.setup_output.setup_to_telegram_dict().
        """
        direction_emoji = "🟢" if setup.get("direction") == "bullish" else "🔴"
        quality_rating = setup.get("quality_rating", "N/A")
        quality_score = setup.get("quality_score", "N/A")
        manual_review = setup.get("requires_manual_review", False)

        message = f"""
{direction_emoji} <b>{setup.get('strategy', 'Setup')} - {setup.get('symbol', 'N/A')}</b>

<b>Direction:</b> {str(setup.get('direction', 'N/A')).upper()}
<b>Quality:</b> {quality_rating} ({quality_score}/8)
"""
        if manual_review:
            message += "<b>⚠️ MANUAL REVIEW REQUIRED - No Quantower level match</b>\n"

        entry = setup.get("entry", 0)
        stop_loss = setup.get("stop_loss", 0)
        take_profit = setup.get("take_profit", 0)
        rr_ratio = setup.get("rr_ratio", 0)
        risk_points = setup.get("risk_points", 0)
        reward_points = setup.get("reward_points", 0)
        key_level = setup.get("key_level", {})
        if isinstance(key_level, dict):
            key_type = key_level.get("type", "N/A")
            key_price = key_level.get("price", 0)
        else:
            key_type = "N/A"
            key_price = 0
        fib_level = setup.get("fib_level", "N/A")
        alignment_quality = setup.get("alignment_quality", "N/A")
        timestamp = setup.get("timestamp")
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S ET") if hasattr(timestamp, "strftime") else str(timestamp)

        entry_note = setup.get("entry_note", "")
        message += f"""
<b>Entry:</b> {entry:.2f} {f'({entry_note})' if entry_note else ''}
<b>Stop Loss:</b> {stop_loss:.2f}
<b>Take Profit:</b> {take_profit:.2f}

<b>Risk/Reward:</b> 1:{rr_ratio:.1f}
<b>Risk:</b> {risk_points:.1f} points
<b>Target:</b> {reward_points:.1f} points

<b>Key Level:</b> {key_type} @ {key_price:.2f}
<b>Fib Level:</b> {fib_level}
<b>Alignment:</b> {alignment_quality}

<i>Generated: {ts_str}</i>
"""
        await self.send_message(message)

    async def send_multiple_setups(self, setups: List[Dict[str, Any]], rate_limit_seconds: float = 0.5):
        """Send alerts for multiple setups."""
        if not setups:
            return
        for setup in setups:
            await self.send_setup_alert(setup)
            await asyncio.sleep(rate_limit_seconds)

    async def send_market_analysis(self, symbol: str, analysis: Dict[str, Any]):
        """Send market structure analysis."""
        message = f"""
📊 <b>Market Analysis - {symbol}</b>

<b>4H Bias:</b> {analysis.get('4h', 'N/A')}
<b>1H Bias:</b> {analysis.get('1h', 'N/A')}
<b>15M Bias:</b> {analysis.get('15m', 'N/A')}

<b>Alignment:</b> {'✅ Aligned' if analysis.get('aligned', False) else '❌ Not Aligned'}

<i>{analysis.get('notes', '')}</i>
"""
        await self.send_message(message)

    async def send_session_start(self, date: str, strategies_enabled: List[str]):
        """Send session start notification."""
        strategies_list = "\n".join([f"  • {s}" for s in strategies_enabled])
        message = f"""
🔔 <b>Trading Session Started</b>

<b>Date:</b> {date}

<b>Active Strategies:</b>
{strategies_list}

<i>Bot is monitoring for setups...</i>
"""
        await self.send_message(message)

    async def send_error(self, error_msg: str):
        """Send error notification."""
        message = f"""
⚠️ <b>Bot Error</b>

{error_msg}

<i>Please check the logs for details.</i>
"""
        await self.send_message(message)
