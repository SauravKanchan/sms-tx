"""Signing Service - Handles threshold ECDSA signing for transactions."""
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union

import requests
from web3 import Web3  # Fallback path if BlockchainService lacks helpers
from eth_account import Account as EthAccount
from hexbytes import HexBytes

from models.database import db_session, User, Transaction, DKGSession, ThresholdShare
from internal.tss import secure_threshold_sign
from utils.config import config

logger = logging.getLogger(__name__)


# ---------- helpers ----------
def eth_to_wei(eth_value: Decimal) -> int:
    return int((Decimal(eth_value) * Decimal(10**18)).to_integral_value())

def wei_to_eth(wei_value: int) -> Decimal:
    return (Decimal(wei_value) / Decimal(10**18)).quantize(Decimal("0.000000000000000001"))
# -----------------------------


class SigningService:
    """Service for handling threshold ECDSA signing."""
    
    def __init__(self, participant_id: int):
        self.participant_id = participant_id
        self.timeout = config.mpc_config.get('timeout_seconds', 30)

    # -----------------------------
    # Web3 utilities (fallbacks)
    # -----------------------------
    def _w3(self) -> Web3:
        return Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 30}))

    def _get_balance_wei_via_web3(self, address: str) -> int:
        w3 = self._w3()
        return int(w3.eth.get_balance(Web3.to_checksum_address(address)))

    def _send_native_via_web3(self, private_key: str, to_address: str, amount_wei: int) -> str:
        """
        Minimal native transfer using Web3 (v5 or v6 compatible).
        Returns tx hash hex string.
        """
        w3 = self._w3()
        acct = EthAccount.from_key(private_key)
        sender = acct.address
        checksum_to = Web3.to_checksum_address(to_address)

        # Nonce
        nonce = w3.eth.get_transaction_count(sender)

        # Detect EIP-1559 support via latest block
        latest_block = w3.eth.get_block("latest")
        eip1559_supported = "baseFeePerGas" in latest_block

        gas_limit = 21000
        tx: Dict[str, Any]

        if eip1559_supported:
            try:
                base = int(latest_block["baseFeePerGas"])
                priority = w3.to_wei(10, "gwei")  # Aggressive priority fee
                max_fee = base * 5 + priority  # Much higher max fee for faster mining
                tx = {
                    "to": checksum_to,
                    "value": int(amount_wei),
                    "nonce": nonce,
                    "chainId": int(config.chain_id),
                    "gas": gas_limit,
                    "maxFeePerGas": int(max_fee),
                    "maxPriorityFeePerGas": int(priority),
                    "type": 2,
                }
            except Exception:
                # fallback to legacy with aggressive pricing
                gas_price = int(w3.eth.gas_price * 3)  # 3x current gas price for fast mining
                tx = {
                    "to": checksum_to,
                    "value": int(amount_wei),
                    "nonce": nonce,
                    "chainId": int(config.chain_id),
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                }
        else:
            gas_price = int(w3.eth.gas_price * 3)  # 3x current gas price for fast mining
            tx = {
                "to": checksum_to,
                "value": int(amount_wei),
                "nonce": nonce,
                "chainId": int(config.chain_id),
                "gas": gas_limit,
                "gasPrice": gas_price,
            }

        signed = w3.eth.account.sign_transaction(tx, private_key=private_key)

        # Web3.py v5 -> signed.rawTransaction ; v6 -> signed.raw_transaction
        raw_tx: Optional[Union[bytes, bytearray]] = getattr(signed, "rawTransaction", None)
        if raw_tx is None:
            raw_tx = getattr(signed, "raw_transaction", None)
        if raw_tx is None:
            try:
                raw_tx = signed["rawTransaction"]  # type: ignore
            except Exception:
                pass
        if raw_tx is None:
            raise RuntimeError("Could not extract raw transaction bytes from SignedTransaction")

        tx_hash = w3.eth.send_raw_transaction(bytes(raw_tx))
        return tx_hash.hex()

    def _wait_for_tx_via_web3(self, tx_hash: str, timeout: int = 180):
        w3 = self._w3()
        return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    # -----------------------------
    # Post-submit confirmation & verification
    # -----------------------------
    def _wait_for_receipt(self, tx_hash: str, timeout: int = 180):
        """
        Wait for a transaction receipt using BlockchainService.wait_for_tx if present,
        else Web3 fallback.
        """
        try:
            from services.blockchain_service import BlockchainService
            bc = BlockchainService()
        except Exception:
            bc = None  # type: ignore

        # Prefer BlockchainService if exposed
        if bc and hasattr(bc, "wait_for_tx"):
            try:
                return bc.wait_for_tx(tx_hash, confirmations=1, timeout=timeout)
            except Exception as e:
                logger.warning(f"wait_for_tx failed in BlockchainService; falling back to Web3: {e}")

        # Fallback to Web3
        return self._wait_for_tx_via_web3(tx_hash, timeout=timeout)

    def _verify_erc20_transfer_in_receipt(self, receipt: Any, token_contract_addr: str,
                                          expected_from: str, expected_to: str) -> Dict[str, Any]:
        """
        Look for an ERC-20 Transfer(from, to, value) event for the given token in the receipt.
        Returns {'found': bool, 'value': int|None}
        """
        try:
            transfer_sig = Web3.keccak(text="Transfer(address,address,uint256)")
            token_addr_checksum = Web3.to_checksum_address(token_contract_addr)
            from_chk = Web3.to_checksum_address(expected_from)
            to_chk = Web3.to_checksum_address(expected_to)

            found_value: Optional[int] = None
            for log in getattr(receipt, "logs", []) or receipt.get("logs", []):
                addr = Web3.to_checksum_address(log["address"])
                if addr != token_addr_checksum:
                    continue
                topics = [HexBytes(t) if isinstance(t, str) else t for t in log["topics"]]
                if len(topics) < 3:
                    continue
                if topics[0] != transfer_sig:
                    continue
                # topics[1], topics[2] are indexed from/to (padded 32-byte)
                from_topic = "0x" + topics[1].hex()[-40:]
                to_topic = "0x" + topics[2].hex()[-40:]
                if Web3.to_checksum_address(from_topic) == from_chk and Web3.to_checksum_address(to_topic) == to_chk:
                    # data holds uint256 value
                    value_int = int(log["data"], 16) if isinstance(log["data"], str) else int(HexBytes(log["data"]).hex(), 16)
                    found_value = value_int
                    return {"found": True, "value": found_value}
            return {"found": False, "value": None}
        except Exception as e:
            logger.warning(f"Error verifying ERC20 Transfer event: {e}")
            return {"found": False, "value": None}

    def _decode_revert_reason(self, tx_hash: str) -> Optional[str]:
        """
        Best-effort revert reason decoder using eth_call replay.
        """
        try:
            w3 = self._w3()
            tx = w3.eth.get_transaction(tx_hash)
            call_obj = {
                "to": tx["to"],
                "from": tx["from"],
                "data": tx["input"],
                "value": tx.get("value", 0),
            }
            # Try a call at the same block as the receipt if possible
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                block_id = receipt["blockNumber"]
            except Exception:
                block_id = "latest"

            try:
                # If this succeeds, there was actually no revert (shouldn't happen with status 0)
                w3.eth.call(call_obj, block_identifier=block_id)
                return None
            except Exception as e:
                # Parse standard Error(string) selector 0x08c379a0
                msg = str(e)
                # Some nodes include data field hex
                data_hex = None
                if hasattr(e, "args") and e.args:
                    # Look for hex string in args
                    for arg in e.args:
                        if isinstance(arg, dict):
                            data_hex = arg.get("data") or arg.get("result")
                        elif isinstance(arg, str) and arg.startswith("0x"):
                            data_hex = arg
                if isinstance(data_hex, (bytes, bytearray)):
                    data_hex = HexBytes(data_hex).hex()
                if isinstance(data_hex, str) and data_hex.startswith("0x"):
                    # Strip function selector
                    if data_hex.startswith("0x08c379a0"):
                        # Error(string)
                        # data = 0x08c379a0 + offset(32) + strlen(32) + string bytes
                        try:
                            # take last bytes for string (simplistic but works in practice)
                            reason_bytes = HexBytes(data_hex)[4+32+32:]
                            # decode utf-8, strip padding
                            reason = reason_bytes.rstrip(b"\x00").decode("utf-8", errors="ignore")
                            return reason or msg
                        except Exception:
                            return msg
                return msg
        except Exception:
            return None

    # -----------------------------
    # Ensure sender has gas
    # -----------------------------
    def _ensure_sender_gas(self, sender_address: str) -> Dict[str, Any]:
        """
        Ensure the sender has enough native ETH to pay gas.
        If below threshold, fund from faucet using config.faucet_private_key
        by the amount config.faucet_amount_eth.
        """
        try:
            # Prefer BlockchainService if it exposes helpers; otherwise use Web3 fallback
            try:
                from services.blockchain_service import BlockchainService
                bc = BlockchainService()
            except Exception:
                bc = None  # type: ignore

            # Faucet amount from config (string/number) -> Decimal
            try:
                faucet_amount_eth = Decimal(str(config.faucet_amount_eth))
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Invalid or missing faucet amount in config.faucet_amount_eth: {e}'
                }
            faucet_amount_wei = eth_to_wei(faucet_amount_eth)

            # Faucet key (env-backed, validated by Config)
            faucet_pk: Optional[str]
            try:
                faucet_pk = config.faucet_private_key
            except Exception as e:
                faucet_pk = None
                logger.warning(f"faucet_private_key not available: {e}")

            # --- Get balance (prefer BlockchainService; fallback to Web3) ---
            balance_wei: Optional[int] = None
            try:
                if bc and hasattr(bc, "get_eth_balance"):
                    res = bc.get_eth_balance(sender_address)
                    balance_wei = int(res["balance_wei"]) if isinstance(res, dict) else int(res)
                elif bc and hasattr(bc, "get_native_balance"):
                    res = bc.get_native_balance(sender_address)
                    balance_wei = int(res["balance_wei"]) if isinstance(res, dict) else int(res)
                else:
                    # Fallback via Web3
                    balance_wei = self._get_balance_wei_via_web3(sender_address)
            except Exception as e:
                # Final fallback via Web3 if service method failed
                logger.warning(f"BlockchainService balance lookup failed; falling back to Web3: {e}")
                balance_wei = self._get_balance_wei_via_web3(sender_address)

            balance_eth = wei_to_eth(balance_wei)
            logger.info(f"[GasCheck] Sender {sender_address} balance: {balance_eth} ETH (threshold {faucet_amount_eth} ETH)")

            if balance_wei >= faucet_amount_wei:
                return {'success': True, 'funded': False, 'balance_eth': str(balance_eth)}

            if not faucet_pk:
                return {
                    'success': False,
                    'error': 'Sender balance below threshold and faucet_private_key not configured'
                }

            # Top up to reach threshold (send only the missing difference)
            topup_amount_wei = faucet_amount_wei - balance_wei
            if topup_amount_wei <= 0:
                return {'success': True, 'funded': False, 'balance_eth': str(balance_eth)}

            logger.info(f"[GasTopUp] Funding {sender_address} with {wei_to_eth(topup_amount_wei)} ETH")

            # --- Send native transfer (prefer BlockchainService; fallback to Web3) ---
            tx_hash: Optional[str] = None
            try:
                if bc and hasattr(bc, "send_native_eth"):
                    tx_hash = bc.send_native_eth(faucet_pk, sender_address, topup_amount_wei)
                elif bc and hasattr(bc, "send_native"):
                    tx_hash = bc.send_native(faucet_pk, sender_address, topup_amount_wei)
                else:
                    # Fallback via Web3
                    tx_hash = self._send_native_via_web3(faucet_pk, sender_address, topup_amount_wei)
            except Exception as e:
                logger.warning(f"BlockchainService native send failed; falling back to Web3: {e}")
                tx_hash = self._send_native_via_web3(faucet_pk, sender_address, topup_amount_wei)

            if not tx_hash:
                return {'success': False, 'error': 'Faucet transfer failed: no tx_hash returned'}

            logger.info(f"[GasTopUp] Faucet transfer submitted: {tx_hash}")

            # Wait 1 conf if service exposes it; else Web3 fallback
            try:
                if bc and hasattr(bc, "wait_for_tx"):
                    bc.wait_for_tx(tx_hash, confirmations=1, timeout=120)
                else:
                    self._wait_for_tx_via_web3(tx_hash, timeout=120)
            except Exception as e:
                logger.warning(f"[GasTopUp] wait_for_tx failed or timed out: {e}. Proceeding anyway.")

            # Re-check balance (best-effort)
            try:
                if bc and hasattr(bc, "get_eth_balance"):
                    res2 = bc.get_eth_balance(sender_address)
                    balance_after = int(res2["balance_wei"]) if isinstance(res2, dict) else int(res2)
                elif bc and hasattr(bc, "get_native_balance"):
                    res2 = bc.get_native_balance(sender_address)
                    balance_after = int(res2["balance_wei"]) if isinstance(res2, dict) else int(res2)
                else:
                    balance_after = self._get_balance_wei_via_web3(sender_address)
            except Exception:
                balance_after = None

            return {
                'success': True,
                'funded': True,
                'tx_hash': tx_hash,
                'balance_eth_after': str(wei_to_eth(balance_after)) if balance_after is not None else None
            }

        except Exception as e:
            logger.error(f"Error ensuring sender gas: {e}")
            return {'success': False, 'error': f'Gas check/top-up failed: {str(e)}'}
    
    # -----------------------------
    # Main flow
    # -----------------------------
    def execute_transaction(self, sender_identifier: str, receiver_identifier: str, amount: str) -> Dict[str, Any]:
        """Execute a USDC transaction using threshold signing."""
        try:
            # Validate users exist and get their addresses
            with db_session() as session:
                sender_user = session.query(User).filter_by(identifier=sender_identifier).first()
                receiver_user = session.query(User).filter_by(identifier=receiver_identifier).first()

                if not sender_user:
                    return {
                        'success': False,
                        'error': f'Sender user not found: {sender_identifier}',
                        'sender': sender_identifier,
                        'receiver': receiver_identifier,
                        'amount': amount
                    }
                if not receiver_user:
                    return {
                        'success': False,
                        'error': f'Receiver user not found: {receiver_identifier}',
                        'sender': sender_identifier,
                        'receiver': receiver_identifier,
                        'amount': amount,
                        'sender_address': sender_user.ethereum_address
                    }

                sender_address = sender_user.ethereum_address
                receiver_address = receiver_user.ethereum_address
            
            logger.info(f"Executing transaction: {sender_identifier} -> {receiver_identifier}, amount: {amount}")

            # Ensure sender has enough gas (with BlockchainService or Web3 fallback)
            gas_res = self._ensure_sender_gas(sender_address)
            if not gas_res.get('success'):
                gas_res.update({
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                })
                return gas_res
            if gas_res.get('funded'):
                logger.info(f"[GasTopUp] Sender funded. Details: {gas_res}")

            # Get threshold shares from database
            shares_result = self._get_stored_threshold_shares(sender_identifier)
            if not shares_result['success']:
                shares_result.update({
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                })
                return shares_result
            
            threshold_shares = shares_result['shares']
            group_pubkey = shares_result['group_pubkey']
            
            # TEMP: Use group pubkey to derive initial sender address for transaction creation
            from internal.eth import pubkey_to_eth_address
            initial_sender_address = pubkey_to_eth_address(group_pubkey)

            logger.info(f"[DEBUG] Database sender address: {sender_address}")
            logger.info(f"[DEBUG] Initial group pubkey derived address: {initial_sender_address}")
            logger.info(f"[DEBUG] Group pubkey: {group_pubkey.hex()[:20]}...")

            # Check if addresses match - throw error if mismatch to prevent wrong wallet usage
            if sender_address.lower() != initial_sender_address.lower():
                error_msg = f"Address mismatch detected! Database address ({sender_address}) != Group pubkey derived address ({initial_sender_address}). Cannot proceed with wrong wallet."
                logger.error(f"[ADDRESS MISMATCH] {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'database_address': sender_address,
                    'derived_address': initial_sender_address
                }

            # Create transaction message for signing using the database address (the original DKG address)
            transaction_data = self._create_transaction_data(
                sender_address=sender_address,
                receiver_address=receiver_address,
                amount=amount
            )
            if not transaction_data['success']:
                transaction_data.update({
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                })
                return transaction_data
            message = transaction_data['message']
            
            # Coordinate threshold signing
            signing_result = self._coordinate_threshold_signing(
                message=message,
                threshold_shares=threshold_shares,
                group_pubkey=group_pubkey,
                sender_identifier=sender_identifier
            )
            if not signing_result['success']:
                signing_result.update({
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                })
                return signing_result

            # Since we already validated address match, use the database address
            logger.info(f"[DEBUG] Using validated database address for transaction: {sender_address}")
            
            # Submit transaction to blockchain
            from services.blockchain_service import BlockchainService
            blockchain_service = BlockchainService()
            submit_result = blockchain_service.submit_transaction(
                transaction_data=transaction_data['tx_data'],
                signature=signing_result['signature']
            )
            if not submit_result.get('success'):
                submit_result.update({
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                })
                return submit_result

            tx_hash = submit_result.get('tx_hash')
            if not tx_hash:
                return {
                    'success': False,
                    'error': 'submit_transaction returned no tx_hash',
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                }

            # Wait for transaction confirmation
            try:
                receipt = self._wait_for_receipt(tx_hash, timeout=30)
            except Exception as e:
                # Store as pending and return success with note
                with db_session() as session:
                    tx = Transaction(
                        sender_identifier=sender_identifier,
                        receiver_identifier=receiver_identifier,
                        sender_address=sender_address,
                        receiver_address=receiver_address,
                        amount=amount,
                        tx_hash=tx_hash,
                        status='pending'
                    )
                    session.add(tx)
                return {'success': True, 'tx_hash': tx_hash, 'sender_address': sender_address, 'receiver_address': receiver_address, 'note': f'Broadcasted; waiting for confirmations failed/timed out: {e}'}

            # Continue with real transaction processing (for real transactions only)
            # Normalize receipt to dict if needed
            if hasattr(receipt, "status"):
                status = int(receipt.status)
                logs = list(getattr(receipt, "logs", []))
            else:
                status = int(receipt.get("status", 0))
                logs = list(receipt.get("logs", []))

            if status != 1:
                reason = self._decode_revert_reason(tx_hash) or "Transaction reverted"
                with db_session() as session:
                    tx = Transaction(
                        sender_identifier=sender_identifier,
                        receiver_identifier=receiver_identifier,
                        sender_address=sender_address,
                        receiver_address=receiver_address,
                        amount=amount,
                        tx_hash=tx_hash,
                        status='failed'
                    )
                    session.add(tx)
                return {
                    'success': False,
                    'error': f'Transaction reverted: {reason}',
                    'tx_hash': tx_hash,
                    'sender': sender_identifier,
                    'receiver': receiver_identifier,
                    'amount': amount,
                    'sender_address': sender_address,
                    'receiver_address': receiver_address
                }

            # Verify ERC-20 Transfer event (USDC)
            verify = self._verify_erc20_transfer_in_receipt(
                receipt=receipt,
                token_contract_addr=config.usdc_contract,
                expected_from=sender_address,
                expected_to=receiver_address
            )

            # Store transaction record
            with db_session() as session:
                tx = Transaction(
                    sender_identifier=sender_identifier,
                    receiver_identifier=receiver_identifier,
                    sender_address=sender_address,
                    receiver_address=receiver_address,
                    amount=amount,
                    tx_hash=tx_hash,
                    status='confirmed' if verify["found"] else 'confirmed_no_event'
                )
                session.add(tx)

            if not verify["found"]:
                logger.warning("Receipt confirmed but did not find expected USDC Transfer event. Check token address and calldata.")

            return {
                'success': True,
                'tx_hash': tx_hash,
                'sender_address': sender_address,
                'receiver_address': receiver_address,
                'transfer_event_found': verify["found"],
                'transfer_value_raw': str(verify["value"]) if verify["value"] is not None else None
            }
            
        except Exception as e:
            logger.error(f"Error executing transaction: {e}")
            # Try to include transaction data if available
            error_response = {
                'success': False,
                'error': f'Transaction execution failed: {str(e)}',
                'sender': sender_identifier,
                'receiver': receiver_identifier,
                'amount': amount
            }
            # Add addresses if they were determined before the error
            try:
                if 'sender_address' in locals():
                    error_response['sender_address'] = locals()['sender_address']
                if 'receiver_address' in locals():
                    error_response['receiver_address'] = locals()['receiver_address']
            except:
                pass
            return error_response
    
    # -----------------------------
    # Existing helpers (DB + TSS)
    # -----------------------------
    def _get_stored_threshold_shares(self, identifier: str) -> Dict[str, Any]:
        """Retrieve threshold shares from database for a user."""
        try:
            with db_session() as session:
                # Get user
                user = session.query(User).filter_by(identifier=identifier).first()
                if not user:
                    return {'success': False, 'error': f'User not found: {identifier}'}

                # Get the completed DKG session for this user
                dkg_session = session.query(DKGSession).filter_by(
                    user_identifier=identifier,
                    status='completed'
                ).order_by(DKGSession.created_at.desc()).first()

                if not dkg_session:
                    return {'success': False, 'error': f'No completed DKG session found for user {identifier}'}

                if not dkg_session.group_public_key:
                    return {'success': False, 'error': 'DKG session missing group public key'}

                # Get threshold shares from database
                threshold_share_records = session.query(ThresholdShare).filter_by(
                    user_identifier=identifier,
                    session_id=dkg_session.session_id
                ).all()

                if not threshold_share_records:
                    return {'success': False, 'error': f'No threshold shares found for user {identifier}'}

                # Convert to the format expected by signing
                threshold_shares = {}
                for share_record in threshold_share_records:
                    threshold_shares[share_record.participant_id] = int(share_record.share_value, 16)

                group_pubkey = bytes.fromhex(dkg_session.group_public_key)

                logger.info(f"Retrieved {len(threshold_shares)} threshold shares from database for user {identifier}")
                logger.info(f"Available participants: {list(threshold_shares.keys())}")

                return {
                    'success': True,
                    'shares': threshold_shares,
                    'group_pubkey': group_pubkey
                }

        except Exception as e:
            logger.error(f"Error retrieving threshold shares: {e}")
            return {'success': False, 'error': f'Failed to retrieve threshold shares: {str(e)}'}
    
    def _create_transaction_data(self, sender_address: str, receiver_address: str, amount: str) -> Dict[str, Any]:
        """Create transaction data for USDC transfer."""
        try:
            from services.blockchain_service import BlockchainService
            blockchain_service = BlockchainService()
            tx_data_result = blockchain_service.create_usdc_transfer_data(
                sender_address=sender_address,
                receiver_address=receiver_address,
                amount=amount
            )
            if not tx_data_result['success']:
                return tx_data_result
            
            tx_data = tx_data_result['tx_data']
            # message for signing:
            message = blockchain_service.get_transaction_hash(tx_data)
            return {'success': True, 'message': message, 'tx_data': tx_data}
        except Exception as e:
            logger.error(f"Error creating transaction data: {e}")
            return {'success': False, 'error': f'Failed to create transaction data: {str(e)}'}
    
    def _coordinate_threshold_signing(self, message: bytes, threshold_shares: Dict[int, int], 
                                    group_pubkey: bytes, sender_identifier: str) -> Dict[str, Any]:
        """Coordinate threshold signing with other participants."""
        try:
            threshold = config.threshold_required
            available_participants = list(threshold_shares.keys())
            if len(available_participants) < threshold:
                return {'success': False, 'error': f'Insufficient participants: got {len(available_participants)}, need {threshold}'}
            
            participants = sorted(available_participants)[:threshold]
            participant_shares = {pid: threshold_shares[pid] for pid in participants}
            logger.info(f"Using participants {participants} for threshold signing")
            
            try:
                r, s, v, actual_pubkey = secure_threshold_sign(
                    participants=participants,
                    shares=participant_shares,
                    message=message,
                    group_pubkey=group_pubkey,
                    threshold=threshold,
                    message_is_hash=True  # message is already a transaction hash
                )
                return {'success': True, 'signature': {'r': r, 's': s, 'v': v, 'pubkey': actual_pubkey}}
            except Exception as e:
                logger.error(f"Threshold signing failed: {e}")
                return {'success': False, 'error': f'Threshold signing failed: {str(e)}'}
        except Exception as e:
            logger.error(f"Error coordinating threshold signing: {e}")
            return {'success': False, 'error': f'Signing coordination failed: {str(e)}'}
    
    def handle_signing_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming signing requests from other participants."""
        try:
            action = data.get('action')
            if action == 'get_share':
                return self._handle_get_share(data)
            elif action == 'partial_sign':
                return self._handle_partial_sign(data)
            else:
                return {'success': False, 'error': f'Unknown signing action: {action}'}
        except Exception as e:
            logger.error(f"Error handling signing request: {e}")
            return {'success': False, 'error': f'Signing request handling failed: {str(e)}'}
    
    def _handle_get_share(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request for threshold share from stored database."""
        try:
            user_identifier = data.get('user_identifier')
            requester = data.get('requester')
            logger.info(f"Share request for user {user_identifier} from participant {requester}")

            # Get shares from database instead of generating on-demand
            shares_result = self._get_stored_threshold_shares(user_identifier)
            if not shares_result['success']:
                return shares_result

            # Return this participant's share
            our_share = shares_result['shares'].get(self.participant_id)
            if our_share is None:
                return {'success': False, 'error': 'Share not found for this participant'}

            return {
                'success': True,
                'share': our_share,
                'participant_id': self.participant_id
            }

        except Exception as e:
            logger.error(f"Error handling get share: {e}")
            return {'success': False, 'error': str(e)}
    
    def _handle_partial_sign(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle partial signing request."""
        # Placeholder
        return {'success': True, 'message': 'Partial signing handled'}
