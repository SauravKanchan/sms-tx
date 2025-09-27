"""Action handlers for address and transaction operations."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def handle_get_address(user_phone: str, dkg_service, db_session) -> Dict[str, Any]:
    """
    Handle address retrieval or creation for a user.

    Args:
        user_phone: 10-digit phone number as string
        dkg_service: DKG service instance
        db_session: Database session class

    Returns:
        Dict containing success status and address info or error
    """
    try:
        # Validate phone number
        if not user_phone or len(user_phone) != 10 or not user_phone.isdigit():
            return {
                'success': False,
                'error': 'Invalid phone number. Must be 10 digits.'
            }

        # Check if user already exists
        from models.database import User
        with db_session() as session:
            user = session.query(User).filter_by(identifier=user_phone).first()

            if user:
                # User exists, return existing address
                logger.info(f"Returning existing address for phone: {user_phone}")
                return {
                    'success': True,
                    'address': user.ethereum_address,
                    'created': False,
                    'identifier': user_phone
                }

        # User doesn't exist, create new address through DKG
        logger.info(f"Creating new address for phone: {user_phone}")

        result = dkg_service.create_user_address(user_phone, 'phone')

        if not result['success']:
            return {
                'success': False,
                'error': result['error']
            }

        return {
            'success': True,
            'address': result['address'],
            'created': True,
            'identifier': user_phone
        }

    except Exception as e:
        logger.error(f"Error in handle_get_address: {e}")
        return {
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }

def handle_transaction(from_phone: str, to_phone: str, amount: float, signing_service) -> Dict[str, Any]:
    """
    Handle transaction execution between users.

    Args:
        from_phone: Sender's 10-digit phone number as string
        to_phone: Receiver's 10-digit phone number as string
        amount: Amount to transfer as float
        signing_service: Signing service instance

    Returns:
        Dict containing success status and transaction info or error
    """
    try:
        # Validate phone numbers
        if not from_phone or len(from_phone) != 10 or not from_phone.isdigit():
            return {
                'success': False,
                'error': 'Invalid sender phone number. Must be 10 digits.'
            }

        if not to_phone or len(to_phone) != 10 or not to_phone.isdigit():
            return {
                'success': False,
                'error': 'Invalid receiver phone number. Must be 10 digits.'
            }

        # Validate amount
        try:
            amount = float(amount)
            if amount <= 0:
                return {
                    'success': False,
                    'error': 'Amount must be positive'
                }
        except (ValueError, TypeError):
            return {
                'success': False,
                    'error': 'Amount must be a valid number'
            }

        # Check that sender and receiver are different
        if from_phone == to_phone:
            return {
                'success': False,
                'error': 'Cannot send money to yourself'
            }

        logger.info(f"Processing transaction: {from_phone} -> {to_phone}, amount: {amount}")

        # Execute transaction through signing service
        result = signing_service.execute_transaction(from_phone, to_phone, amount)

        if not result['success']:
            return {
                'success': False,
                'error': result['error']
            }

        return {
            'success': True,
            'tx_hash': result['tx_hash'],
            'sender_address': result['sender_address'],
            'receiver_address': result['receiver_address'],
            'amount': amount
        }

    except Exception as e:
        logger.error(f"Error in handle_transaction: {e}")
        return {
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }