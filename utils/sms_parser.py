"""SMS Intent Parser - Fast regex-based parsing for structured SMS messages."""
import re
import logging
from typing import Dict, Union

logger = logging.getLogger(__name__)

def parse_sms_fallback(text: str) -> Dict[str, Union[str, int, float]]:
    """
    Fallback intent parser (regex-based).

    Rules:
    - Input format: 'from=<SENDER>: <MESSAGE>'
    - Normalize phones by digits only; use the last 10 digits as the phone.
    - If MESSAGE contains a number (int or float) ⇒ treat as transaction:
        * amount = first number found (int if integral, else float)
        * to = first 10-digit phone in MESSAGE that is not the sender (else first 10-digit if none differ)
        * If no 10-digit phone found in MESSAGE ⇒ unknown (missing recipient phone)
    - If MESSAGE has no numbers ⇒ treat as get-address for the sender.

    Returns JSON-like dicts:
      {"type":"get-address","user":"<10-digit>"}
      {"type":"transaction","from":"<10-digit>","to":"<10-digit>","amount":<number>}
      {"type":"unknown","reason":"<short>"}
    """
    logger.info(f"Parsing SMS with regex parser: {text[:100]}...")

    # Split into sender and message
    m = re.match(r'^\s*from\s*=\s*([+\d\-\s()]+)\s*:\s*(.+)\s*$', text, flags=re.IGNORECASE)
    if not m:
        logger.warning(f"Invalid input format for regex parser: {text[:50]}...")
        return {"type": "unknown", "reason": "invalid input format"}

    sender_raw, message = m.group(1), m.group(2)

    # Normalize sender to 10 digits (take last 10 digits to handle country codes)
    sender_digits = re.sub(r'\D', '', sender_raw)
    if len(sender_digits) < 10:
        logger.warning(f"Sender phone too short: {sender_raw} -> {sender_digits}")
        return {"type": "unknown", "reason": "sender phone too short"}
    sender = sender_digits[-10:]

    # Check for balance keyword first (high priority)
    balance_match = re.search(r'\bbalances?\b', message, re.IGNORECASE)
    if balance_match:
        logger.info(f"Balance keyword detected - treating as get-balance for {sender}")
        return {"type": "get-balance", "user": sender}

    # Find first numeric amount (int or float)
    num_match = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])', message)
    if not num_match:
        # No number ⇒ address intent for sender
        logger.info(f"No number found in message - treating as get-address for {sender}")
        return {"type": "get-address", "user": sender}

    # Parse amount as int if integral, else float
    amount_str = num_match.group(1)
    amount = float(amount_str)
    amount = int(amount) if amount.is_integer() else amount

    # Find 10-digit phone(s) in the message
    phones_in_msg = re.findall(r'(?<!\d)(\d{10})(?!\d)', message)

    # Prefer a recipient different from sender, else fall back to the first found
    recipient = None
    for p in phones_in_msg:
        if p != sender:
            recipient = p
            break
    if recipient is None and phones_in_msg:
        recipient = phones_in_msg[0]

    if not recipient:
        logger.warning(f"No recipient phone found in transaction message: {message}")
        return {"type": "unknown", "reason": "missing recipient phone"}

    logger.info(f"Successfully parsed transaction: {sender} -> {recipient}, amount: {amount}")
    return {
        "type": "transaction",
        "from": sender,
        "to": recipient,
        "amount": amount
    }