"""MPC Signature Server - Threshold ECDSA service."""
import argparse
import logging
import sys
from typing import Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

from utils.config import config
from models.database import init_database, db_session
from services.dkg_service import DKGService
from services.signing_service import SigningService
from services.blockchain_service import BlockchainService
from utils.action_handlers import handle_get_address, handle_transaction
from utils.phone_validator import validate_transaction_phones, validate_phone_number
from asi1.asi1_client import ASI1Client, load_prompt_template

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global services
participant_id: int = 0
dkg_service: DKGService = None
signing_service: SigningService = None
blockchain_service: BlockchainService = None
asi1_client: ASI1Client = None


def create_app(participant_id: int) -> Flask:
    """Create and configure the Flask application."""
    global dkg_service, signing_service, blockchain_service, asi1_client

    # Ensure data directory exists
    config.ensure_data_directory()

    # Initialize database
    init_database()

    # Initialize services
    dkg_service = DKGService(participant_id)
    signing_service = SigningService(participant_id)
    blockchain_service = BlockchainService()
    asi1_client = ASI1Client()

    logger.info(f"MPC Signature Server initialized (Participant {participant_id})")

    return app


@app.route('/api/address', methods=['POST'])
def get_address():
    """Get or create Ethereum address for a user identifier."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body must be valid JSON'
            }), 400

        identifier = data.get('identifier')
        identifier_type = data.get('type', 'email')

        if not identifier:
            return jsonify({
                'success': False,
                'error': 'identifier field is required'
            }), 400

        # For backward compatibility, handle both phone and email identifiers
        if identifier_type == 'phone' or (len(identifier) == 10 and identifier.isdigit()):
            # Use phone handler for phone numbers
            result = handle_get_address(identifier, dkg_service, db_session)
        else:
            # Fallback to original logic for emails and other identifiers
            from models.database import User
            with db_session() as session:
                user = session.query(User).filter_by(identifier=identifier).first()

                if user:
                    # User exists, return existing address
                    result = {
                        'success': True,
                        'address': user.ethereum_address,
                        'created': False,
                        'identifier': identifier
                    }
                else:
                    # User doesn't exist, create new address through DKG
                    logger.info(f"Creating new address for identifier: {identifier}")
                    dkg_result = dkg_service.create_user_address(identifier, identifier_type)

                    if not dkg_result['success']:
                        result = {
                            'success': False,
                            'error': dkg_result['error']
                        }
                    else:
                        result = {
                            'success': True,
                            'address': dkg_result['address'],
                            'created': True,
                            'identifier': identifier
                        }

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400 if 'Invalid' in result.get('error', '') else 500

    except Exception as e:
        logger.error(f"Error in get_address: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/transaction', methods=['POST'])
def create_transaction():
    """Execute a USDC transaction between users."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body must be valid JSON'
            }), 400

        sender = data.get('sender')
        receiver = data.get('receiver')
        amount = data.get('amount')

        if not all([sender, receiver, amount]):
            return jsonify({
                'success': False,
                'error': 'sender, receiver, and amount fields are required'
            }), 400

        # Check if sender and receiver are phone numbers (10 digits)
        if (len(str(sender)) == 10 and str(sender).isdigit() and
            len(str(receiver)) == 10 and str(receiver).isdigit()):
            # Use phone handler for phone-to-phone transactions
            result = handle_transaction(str(sender), str(receiver), amount, signing_service)
        else:
            # Fallback to original logic for other identifiers
            try:
                float(amount)
            except (ValueError, TypeError):
                return jsonify({
                    'success': False,
                    'error': 'amount must be a valid number'
                }), 400

            logger.info(f"Processing transaction: {sender} -> {receiver}, amount: {amount}")
            logger.info(f"Executing transaction through signing service")

            # Execute transaction through signing service
            tx_result = signing_service.execute_transaction(sender, receiver, amount)

            if not tx_result['success']:
                result = {
                    'success': False,
                    'error': tx_result['error']
                }
            else:
                result = {
                    'success': True,
                    'tx_hash': tx_result['tx_hash'],
                    'sender_address': tx_result['sender_address'],
                    'receiver_address': tx_result['receiver_address'],
                    'amount': amount
                }

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error in create_transaction: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/ai', methods=['POST'])
def handle_ai_message():
    """Process human language messages using ASI1 AI and execute appropriate actions."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body must be valid JSON'
            }), 400

        message = data.get('message')
        if not message:
            return jsonify({
                'success': False,
                'error': 'message field is required'
            }), 400

        logger.info(f"Processing AI message: {message}")

        # Load system prompt template
        try:
            system_prompt = load_prompt_template()
        except Exception as e:
            logger.error(f"Failed to load prompt template: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to load AI prompt configuration'
            }), 500

        # Extract intent using ASI1 AI
        ai_result = asi1_client.extract_intent(message, system_prompt)

        if not ai_result['success']:
            return jsonify({
                'success': False,
                'error': f"AI processing failed: {ai_result['error']}"
            }), 500

        intent = ai_result['intent']
        logger.info(f"Extracted intent: {intent}")

        # Route based on intent type
        intent_type = intent.get('type')

        if intent_type == 'get-address':
            user_phone = intent.get('user')
            if not user_phone:
                return jsonify({
                    'success': False,
                    'error': 'Missing user phone number in intent'
                }), 400

            result = handle_get_address(user_phone, dkg_service, db_session)

        elif intent_type == 'transaction':
            from_phone = intent.get('from')
            to_phone = intent.get('to')
            amount = intent.get('amount')

            if not all([from_phone, to_phone, amount]):
                return jsonify({
                    'success': False,
                    'error': 'Missing transaction parameters in intent'
                }), 400

            # Validate phone numbers before processing transaction
            logger.info(f"Validating transaction phone numbers: from={from_phone}, to={to_phone}")

            phone_validation = validate_transaction_phones(from_phone, to_phone)

            if not phone_validation.is_valid:
                error_msg = f"Invalid phone numbers: {', '.join(phone_validation.errors)}"
                logger.warning(f"Transaction rejected due to invalid phone numbers: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400

            # Use validated phone numbers for transaction
            validated_from = phone_validation.formatted_from
            validated_to = phone_validation.formatted_to

            logger.info(f"Phone validation successful - proceeding with transaction: {validated_from} -> {validated_to}")

            result = handle_transaction(validated_from, validated_to, amount, signing_service)

            # If transaction was successful, ensure the response includes the validated phone numbers
            if result.get('success') and isinstance(result, dict):
                result['from'] = validated_from
                result['to'] = validated_to

        elif intent_type == 'unknown':
            reason = intent.get('reason', 'Unable to understand the message')
            return jsonify({
                'success': False,
                'error': f"Unable to process message: {reason}",
                'intent': intent
            }), 400

        else:
            return jsonify({
                'success': False,
                'error': f"Unsupported intent type: {intent_type}",
                'intent': intent
            }), 400

        # Return the result
        if result['success']:
            # Remove 'success' field and return all other fields at top level
            response_data = {k: v for k, v in result.items() if k != 'success'}
            return jsonify(response_data)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error in handle_ai_message: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/fund', methods=['POST'])
def fund_address():
    """Fund an address with ETH from faucet."""
    try:
        data = request.get_json()
        if not data or 'address' not in data:
            return jsonify({
                'success': False,
                'error': 'Address is required'
            }), 400

        address = data['address']
        result = blockchain_service.fund_address(address)

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error in fund_address: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get server status and health information."""
    try:
        # Check peer connectivity
        peers = {}
        other_servers = config.get_other_servers(participant_id)
        
        for server in other_servers:
            try:
                import requests
                url = f"http://{server['host']}:{server['api_port']}/api/ping"
                response = requests.get(url, timeout=5)
                peers[str(server['id'])] = "connected" if response.status_code == 200 else "error"
            except:
                peers[str(server['id'])] = "disconnected"
        
        # Check database connectivity
        database_status = "connected"
        try:
            with db_session() as session:
                session.execute("SELECT 1")
        except:
            database_status = "error"
        
        # Check blockchain connectivity
        blockchain_status = blockchain_service.check_connection()
        
        return jsonify({
            'success': True,
            'participant_id': participant_id,
            'status': 'healthy',
            'peers': peers,
            'database': database_status,
            'blockchain': blockchain_status['status']
        })
        
    except Exception as e:
        logger.error(f"Error in get_status: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/ping', methods=['GET'])
def ping():
    """Health check endpoint for peer connectivity."""
    return jsonify({
        'success': True,
        'participant_id': participant_id,
        'status': 'healthy'
    })


@app.route('/mpc/dkg', methods=['POST'])
def handle_dkg_request():
    """Handle DKG requests from other participants."""
    try:
        data = request.get_json()
        result = dkg_service.handle_dkg_request(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in handle_dkg_request: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/mpc/sign', methods=['POST'])
def handle_signing_request():
    """Handle threshold signing requests from other participants."""
    try:
        data = request.get_json()
        result = signing_service.handle_signing_request(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in handle_signing_request: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def main():
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description='MPC Signature Server')
    parser.add_argument('--participant-id', type=int, required=True,
                       help='Participant ID (1, 2, or 3)')
    args = parser.parse_args()
    
    if args.participant_id not in [1, 2, 3]:
        print("Error: participant-id must be 1, 2, or 3")
        sys.exit(1)
    
    global participant_id
    participant_id = args.participant_id
    
    # Create app
    app = create_app(participant_id)
    
    # Get server configuration
    server_config = config.get_server_config(participant_id)
    
    # Run server
    logger.info(f"Starting MPC Signature Server on port {server_config['api_port']}")
    app.run(
        host='0.0.0.0',
        port=server_config['api_port'],
        debug=False
    )


if __name__ == '__main__':
    main()