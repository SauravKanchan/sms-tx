"""Blockchain Service - Handles Web3 interactions with Base network."""
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from web3 import Web3
from eth_account import Account

# Import POA middleware with compatibility for different web3.py versions
try:
    from web3.middleware.geth_poa import geth_poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        # For newer versions of web3.py
        geth_poa_middleware = None
from utils.config import config

logger = logging.getLogger(__name__)

# USDC ERC-20 ABI (minimal for transfers)
USDC_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


class BlockchainService:
    """Service for blockchain interactions."""
    
    def __init__(self):
        self.rpc_url = config.rpc_url
        self.chain_id = config.chain_id
        self.usdc_contract = config.usdc_contract
        self.faucet_private_key = config.faucet_private_key
        self.faucet_amount_eth = config.faucet_amount_eth
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        # Add POA middleware for Base network if available
        if geth_poa_middleware is not None:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Initialize USDC contract
        self.usdc_contract_instance = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.usdc_contract),
            abi=USDC_ABI
        )
        
        # Get faucet account
        if self.faucet_private_key.startswith('0x'):
            self.faucet_account = Account.from_key(self.faucet_private_key)
        else:
            self.faucet_account = Account.from_key('0x' + self.faucet_private_key)
    
    def check_connection(self) -> Dict[str, Any]:
        """Check blockchain connection status."""
        try:
            # Test connection by getting latest block
            latest_block = self.w3.eth.get_block('latest')
            
            return {
                'success': True,
                'status': 'connected',
                'block_number': latest_block['number'],
                'chain_id': self.w3.eth.chain_id
            }
            
        except Exception as e:
            logger.error(f"Blockchain connection error: {e}")
            return {
                'success': False,
                'status': 'error',
                'error': str(e)
            }
    
    def fund_address(self, address: str) -> Dict[str, Any]:
        """Fund an address with ETH from faucet."""
        try:
            # Check current balance
            balance = self.w3.eth.get_balance(Web3.to_checksum_address(address))
            balance_eth = self.w3.from_wei(balance, 'ether')
            
            logger.info(f"Current balance for {address}: {balance_eth} ETH")
            
            # Only fund if balance is low (less than 0.0001 ETH)
            if balance_eth >= 0.0001:
                return {
                    'success': True,
                    'message': 'Address already has sufficient ETH',
                    'balance': str(balance_eth)
                }
            
            # Prepare funding transaction
            amount_wei = self.w3.to_wei(Decimal(self.faucet_amount_eth), 'ether')
            
            # Get nonce for faucet account
            nonce = self.w3.eth.get_transaction_count(self.faucet_account.address)
            
            # Get gas price (aggressive pricing for fast mining)
            gas_price = self.w3.eth.gas_price * 3
            
            # Build transaction
            transaction = {
                'to': Web3.to_checksum_address(address),
                'value': amount_wei,
                'gas': 21000,  # Standard ETH transfer gas
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.chain_id
            }
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.faucet_private_key)

            # Send transaction (handle different Web3.py versions)
            raw_transaction = getattr(signed_txn, 'rawTransaction', getattr(signed_txn, 'raw_transaction', None))
            if raw_transaction is None:
                raise ValueError("Could not access raw transaction from signed transaction")

            tx_hash = self.w3.eth.send_raw_transaction(raw_transaction)
            
            logger.info(f"Funding transaction sent: {tx_hash.hex()}")
            
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'amount': self.faucet_amount_eth
            }
            
        except Exception as e:
            logger.error(f"Error funding address {address}: {e}")
            return {
                'success': False,
                'error': f'Funding failed: {str(e)}'
            }
    
    def get_usdc_balance(self, address: str) -> Dict[str, Any]:
        """Get USDC balance for an address."""
        try:
            checksum_address = Web3.to_checksum_address(address)
            
            # Get balance from USDC contract
            balance_raw = self.usdc_contract_instance.functions.balanceOf(checksum_address).call()
            
            # USDC has 6 decimals
            balance = balance_raw / (10**6)
            
            return {
                'success': True,
                'balance': str(balance),
                'balance_raw': balance_raw
            }
            
        except Exception as e:
            logger.error(f"Error getting USDC balance for {address}: {e}")
            return {
                'success': False,
                'error': f'Failed to get USDC balance: {str(e)}'
            }
    
    def create_usdc_transfer_data(self, sender_address: str, receiver_address: str, amount: str) -> Dict[str, Any]:
        """Create USDC transfer transaction data."""
        try:
            # Convert amount to USDC units (6 decimals)
            amount_decimal = Decimal(amount)
            amount_raw = int(amount_decimal * (10**6))
            
            # Validate addresses
            sender_checksum = Web3.to_checksum_address(sender_address)
            receiver_checksum = Web3.to_checksum_address(receiver_address)
            
            # Check sender USDC balance
            balance_result = self.get_usdc_balance(sender_address)
            if not balance_result['success']:
                return balance_result

            logger.info(f"[USDC Balance Check] Sender: {sender_address}, Balance: {balance_result['balance']} USDC, Required: {amount} USDC")

            if Decimal(balance_result['balance']) < amount_decimal:
                return {
                    'success': False,
                    'error': f'Insufficient USDC balance: {balance_result["balance"]} < {amount}',
                    'sender_address': sender_address,
                    'receiver_address': receiver_address,
                    'amount': amount,
                    'current_balance': balance_result['balance']
                }
            
            # Get nonce for sender
            nonce = self.w3.eth.get_transaction_count(sender_checksum)
            
            # Get gas price (aggressive pricing for fast mining)
            gas_price = self.w3.eth.gas_price * 3
            
            # Build USDC transfer transaction
            transaction = self.usdc_contract_instance.functions.transfer(
                receiver_checksum,
                amount_raw
            ).build_transaction({
                'from': sender_checksum,
                'gas': 100000,  # Estimate gas for USDC transfer
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.chain_id
            })
            
            return {
                'success': True,
                'tx_data': transaction
            }
            
        except Exception as e:
            logger.error(f"Error creating USDC transfer data: {e}")
            return {
                'success': False,
                'error': f'Failed to create transaction data: {str(e)}'
            }
    
    def get_transaction_hash(self, tx_data: Dict[str, Any]) -> bytes:
        """Get proper Ethereum transaction hash for signing using RLP encoding."""
        try:
            from rlp import encode
            from eth_utils import to_bytes, keccak

            # Create unsigned transaction array for RLP encoding (EIP-155 format)
            tx_array = [
                tx_data['nonce'],
                tx_data['gasPrice'],
                tx_data['gas'],
                to_bytes(hexstr=tx_data['to']),
                tx_data.get('value', 0),
                to_bytes(hexstr=tx_data.get('data', '0x')) if tx_data.get('data') else b'',
                tx_data['chainId'],
                0,  # r placeholder for unsigned transaction
                0   # s placeholder for unsigned transaction
            ]

            # RLP encode and hash according to EIP-155
            encoded = encode(tx_array)
            transaction_hash = keccak(encoded)

            # Debug logging for data field conversion
            data_field = tx_data.get('data', '')
            if data_field:
                logger.info(f"[DEBUG] Transaction data converted: {data_field[:42]}... -> {len(to_bytes(hexstr=data_field))} bytes")

            logger.info(f"[DEBUG] Created proper Ethereum transaction hash: {transaction_hash.hex()}")
            return transaction_hash

        except Exception as e:
            logger.error(f"Error creating transaction hash: {e}")
            raise
    
    def submit_transaction(self, transaction_data: Dict[str, Any], signature: Dict[str, Any]) -> Dict[str, Any]:
        """Submit signed transaction to the blockchain."""
        try:
            r = signature['r']
            s = signature['s']
            v = signature['v']

            logger.info(f"[DEBUG] Submitting transaction with signature: r={hex(r)[:10]}..., s={hex(s)[:10]}..., v={v}")
            logger.info(f"[DEBUG] Transaction data: {transaction_data}")

            # Create signed transaction for submission
            try:
                # Simplified approach: Use Web3 to sign and submit
                from eth_account import Account

                # Create basic transaction structure
                unsigned_tx = {
                    'nonce': transaction_data['nonce'],
                    'gasPrice': transaction_data['gasPrice'],
                    'gas': transaction_data['gas'],
                    'to': transaction_data['to'],
                    'value': transaction_data.get('value', 0),
                    'data': transaction_data.get('data', b''),
                    'chainId': transaction_data['chainId']
                }

                # Reconstruct signature
                signature_bytes = r.to_bytes(32, 'big') + s.to_bytes(32, 'big') + bytes([v])

                # Create signed transaction object
                signed_tx_dict = {**unsigned_tx, 'r': r, 's': s, 'v': v}

                # Encode transaction manually for submission
                from rlp import encode
                from eth_utils import to_bytes

                # EIP-155 signed transaction encoding
                # Convert v from recovery format (27/28) to EIP-155 format
                chain_id = unsigned_tx['chainId']
                eip155_v = v + chain_id * 2 + 35 - 27  # Convert 27/28 to EIP-155 format

                logger.info(f"[DEBUG] V conversion: recovery_v={v}, chain_id={chain_id}, eip155_v={eip155_v}")

                tx_array = [
                    unsigned_tx['nonce'],
                    unsigned_tx['gasPrice'],
                    unsigned_tx['gas'],
                    to_bytes(hexstr=unsigned_tx['to']),
                    unsigned_tx['value'],
                    to_bytes(hexstr=unsigned_tx['data']) if unsigned_tx['data'] else b'',
                    eip155_v,  # Use EIP-155 v value
                    r,
                    s
                ]

                encoded_tx = encode(tx_array)

                logger.info(f"[DEBUG] Encoded transaction length: {len(encoded_tx)} bytes")

                # Submit to blockchain
                tx_hash = self.w3.eth.send_raw_transaction(encoded_tx)
                tx_hash_str = tx_hash.hex()

                logger.info(f"[SUCCESS] Real transaction submitted: {tx_hash_str}")

                return {
                    'success': True,
                    'tx_hash': tx_hash_str
                }

            except Exception as submit_error:
                logger.error(f"Real transaction submission failed: {submit_error}")
                return {
                    'success': False,
                    'error': f'Transaction submission failed: {str(submit_error)}'
                }
            
        except Exception as e:
            logger.error(f"Error submitting transaction: {e}")
            return {
                'success': False,
                'error': f'Transaction submission failed: {str(e)}'
            }
    
    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction status and receipt."""
        try:
            # Get transaction receipt
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            return {
                'success': True,
                'status': 'confirmed' if receipt['status'] == 1 else 'failed',
                'block_number': receipt['blockNumber'],
                'gas_used': receipt['gasUsed'],
                'transaction_fee': str(receipt['gasUsed'] * receipt['effectiveGasPrice'])
            }
            
        except Exception as e:
            logger.error(f"Error getting transaction status for {tx_hash}: {e}")
            return {
                'success': False,
                'error': f'Failed to get transaction status: {str(e)}'
            }