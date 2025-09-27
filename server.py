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


def create_app(participant_id: int) -> Flask:
    """Create and configure the Flask application."""
    global dkg_service, signing_service, blockchain_service
    
    # Ensure data directory exists
    config.ensure_data_directory()
    
    # Initialize database
    init_database()
    
    # Initialize services
    dkg_service = DKGService(participant_id)
    signing_service = SigningService(participant_id)
    blockchain_service = BlockchainService()
    
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
        
        # Check if user already exists
        from models.database import User
        with db_session() as session:
            user = session.query(User).filter_by(identifier=identifier).first()
            
            if user:
                # User exists, return existing address
                return jsonify({
                    'success': True,
                    'address': user.ethereum_address,
                    'created': False,
                    'identifier': identifier
                })
        
        # User doesn't exist, create new address through DKG
        logger.info(f"Creating new address for identifier: {identifier}")
        
        result = dkg_service.create_user_address(identifier, identifier_type)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 500
        
        # Fund new address with ETH
        try:
            fund_result = blockchain_service.fund_address(result['address'])
            if not fund_result['success']:
                logger.warning(f"Failed to fund address {result['address']}: {fund_result['error']}")
        except Exception as e:
            logger.warning(f"Error funding address: {e}")
        
        return jsonify({
            'success': True,
            'address': result['address'],
            'created': True,
            'identifier': identifier
        })
        
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
        
        # Validate amount
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
        result = signing_service.execute_transaction(sender, receiver, amount)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
        
        return jsonify({
            'success': True,
            'tx_hash': result['tx_hash'],
            'sender_address': result['sender_address'],
            'receiver_address': result['receiver_address'],
            'amount': amount
        })
        
    except Exception as e:
        logger.error(f"Error in create_transaction: {e}")
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