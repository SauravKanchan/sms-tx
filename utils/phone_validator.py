"""Phone number validation utility for backend."""
import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PhoneValidationResult:
    """Result of phone number validation."""

    def __init__(self, is_valid: bool, formatted_number: Optional[str] = None, error: Optional[str] = None):
        self.is_valid = is_valid
        self.formatted_number = formatted_number
        self.error = error

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'is_valid': self.is_valid,
            'formatted_number': self.formatted_number,
            'error': self.error
        }


class TransactionPhoneValidationResult:
    """Result of transaction phone numbers validation."""

    def __init__(self, is_valid: bool, formatted_from: Optional[str] = None,
                 formatted_to: Optional[str] = None, errors: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.formatted_from = formatted_from
        self.formatted_to = formatted_to
        self.errors = errors or []

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'is_valid': self.is_valid,
            'formatted_from': self.formatted_from,
            'formatted_to': self.formatted_to,
            'errors': self.errors
        }


class PhoneValidator:
    """Phone number validation utility class."""

    @staticmethod
    def validate_phone_number(phone_number: str, field_name: str = 'phone') -> PhoneValidationResult:
        """
        Validate and format a phone number to 10-digit Indian mobile format.

        Args:
            phone_number: Raw phone number to validate
            field_name: Field name for debugging (e.g., 'from', 'to')

        Returns:
            PhoneValidationResult with validation status and formatted number
        """
        if not phone_number:
            error = f"{field_name} phone number is required"
            logger.warning(f"Phone validation failed: {error}")
            return PhoneValidationResult(False, None, error)

        if not isinstance(phone_number, str):
            error = f"{field_name} phone number must be a string"
            logger.warning(f"Phone validation failed: {error}")
            return PhoneValidationResult(False, None, error)

        # Remove all whitespace and non-digit characters
        cleaned = re.sub(r'\D', '', phone_number.strip())

        if not cleaned:
            error = f"{field_name} phone number contains no digits"
            logger.warning(f"Phone validation failed: {error} (original: {phone_number})")
            return PhoneValidationResult(False, None, error)

        # Remove +91 country code if present
        if cleaned.startswith('91') and len(cleaned) == 12:
            cleaned = cleaned[2:]
            logger.info(f"Removed +91 prefix from {field_name} phone number: {phone_number} -> {cleaned}")

        # Validate exactly 10 digits
        if len(cleaned) != 10:
            error = f"{field_name} phone number must be exactly 10 digits, got {len(cleaned)}"
            logger.warning(f"Phone validation failed: {error} (original: {phone_number}, cleaned: {cleaned})")
            return PhoneValidationResult(False, None, error)

        # Validate all characters are digits
        if not cleaned.isdigit():
            error = f"{field_name} phone number must contain only digits"
            logger.warning(f"Phone validation failed: {error} (original: {phone_number}, cleaned: {cleaned})")
            return PhoneValidationResult(False, None, error)

        # Additional validation for Indian mobile numbers (should start with 6-9)
        if not re.match(r'^[6-9]', cleaned):
            error = f"{field_name} phone number should start with 6, 7, 8, or 9"
            logger.warning(f"Phone validation failed: {error} (original: {phone_number}, cleaned: {cleaned})")
            return PhoneValidationResult(False, None, error)

        logger.info(f"Phone validation successful for {field_name}: {phone_number} -> {cleaned}")
        return PhoneValidationResult(True, cleaned, None)

    @classmethod
    def validate_transaction_phones(cls, from_phone: str, to_phone: str) -> TransactionPhoneValidationResult:
        """
        Validate transaction phone numbers (both from and to).

        Args:
            from_phone: Sender phone number
            to_phone: Recipient phone number

        Returns:
            TransactionPhoneValidationResult with validation status and formatted numbers
        """
        errors = []
        formatted_from = None
        formatted_to = None

        # Validate from phone
        from_result = cls.validate_phone_number(from_phone, 'from')
        if not from_result.is_valid:
            errors.append(from_result.error)
        else:
            formatted_from = from_result.formatted_number

        # Validate to phone
        to_result = cls.validate_phone_number(to_phone, 'to')
        if not to_result.is_valid:
            errors.append(to_result.error)
        else:
            formatted_to = to_result.formatted_number

        # Check if from and to are the same
        if formatted_from and formatted_to and formatted_from == formatted_to:
            error = 'Sender and recipient phone numbers cannot be the same'
            errors.append(error)
            logger.warning(f"Transaction validation failed: {error} (from: {from_phone}, to: {to_phone})")

        is_valid = len(errors) == 0

        if is_valid:
            logger.info(f"Transaction phone validation successful: from={from_phone}->{formatted_from}, to={to_phone}->{formatted_to}")
        else:
            logger.error(f"Transaction phone validation failed: from={from_phone}, to={to_phone}, errors={errors}")

        return TransactionPhoneValidationResult(is_valid, formatted_from, formatted_to, errors)

    @staticmethod
    def format_phone_number(phone_number: str) -> str:
        """
        Simple phone number formatting (legacy compatibility).

        Args:
            phone_number: Raw phone number

        Returns:
            Formatted 10-digit phone number or original if invalid
        """
        if not phone_number:
            return ''

        # Remove all non-digit characters
        cleaned = re.sub(r'\D', '', phone_number)

        # Remove +91 country code if present
        if cleaned.startswith('91') and len(cleaned) == 12:
            cleaned = cleaned[2:]

        # Return 10-digit number if valid, otherwise return as-is
        if len(cleaned) == 10 and cleaned.isdigit():
            return cleaned

        # Log warning for unexpected length
        logger.warning(f"Unexpected phone number length: {cleaned} (length: {len(cleaned)})")
        return cleaned

    @staticmethod
    def is_valid_phone_number(phone_number: str) -> bool:
        """
        Simple validation check for phone number.

        Args:
            phone_number: Phone number to validate

        Returns:
            True if valid 10-digit number
        """
        formatted = PhoneValidator.format_phone_number(phone_number)
        return len(formatted) == 10 and formatted.isdigit() and re.match(r'^[6-9]', formatted)


# Convenience functions for backward compatibility
def validate_phone_number(phone_number: str, field_name: str = 'phone') -> PhoneValidationResult:
    """Validate a single phone number."""
    return PhoneValidator.validate_phone_number(phone_number, field_name)


def validate_transaction_phones(from_phone: str, to_phone: str) -> TransactionPhoneValidationResult:
    """Validate transaction phone numbers."""
    return PhoneValidator.validate_transaction_phones(from_phone, to_phone)


def format_phone_number(phone_number: str) -> str:
    """Format phone number to 10-digit format."""
    return PhoneValidator.format_phone_number(phone_number)


def is_valid_phone_number(phone_number: str) -> bool:
    """Check if phone number is valid."""
    return PhoneValidator.is_valid_phone_number(phone_number)