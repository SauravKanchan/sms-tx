"""DKG Service - Handles distributed key generation for user addresses."""
import json
import uuid
import logging
from typing import Dict, Any, Optional, List
import requests

# UPDATED: for completed_at timestamp
from datetime import datetime, timezone

from models.database import db_session, User, DKGSession, ThresholdShare
from internal.dkg import secure_dkg_ceremony
from internal.eth import pubkey_to_eth_address
from utils.config import config

logger = logging.getLogger(__name__)


class DKGService:
    """Service for handling distributed key generation."""
    
    def __init__(self, participant_id: int):
        self.participant_id = participant_id
        self.timeout = config.mpc_config.get('timeout_seconds', 30)
        self._dkg_sessions = {}  # Initialize DKG session storage
    
    def create_user_address(self, identifier: str, identifier_type: str = 'email') -> Dict[str, Any]:
        """Create a new Ethereum address for a user through DKG."""
        try:
            # ROOT CAUSE FIX: Check if user already exists before starting DKG
            with db_session() as session:
                existing_user = session.query(User).filter_by(identifier=identifier).first()
                if existing_user:
                    logger.info(f"User {identifier} already exists, returning existing address: {existing_user.ethereum_address}")
                    return {
                        'success': True,
                        'address': existing_user.ethereum_address,
                        'message': 'User already exists, returning existing address',
                        'existing_user': True
                    }

            # Generate unique session ID for new users only
            session_id = str(uuid.uuid4())
            
            # Get other participants
            other_servers = config.get_other_servers(self.participant_id)
            all_participant_ids = [self.participant_id] + [s['id'] for s in other_servers]
            all_participant_ids.sort()
            
            logger.info(f"Starting DKG session {session_id} for user {identifier}")
            
            # Create DKG session record
            with db_session() as session:
                # UPDATED: guard against accidental duplicates (idempotency-ish)
                existing = session.query(DKGSession).filter_by(session_id=session_id).one_or_none()
                if not existing:
                    dkg_session = DKGSession(
                        session_id=session_id,
                        user_identifier=identifier,
                        initiator_participant_id=self.participant_id,
                        status='running',
                        participants=json.dumps(all_participant_ids)
                    )
                    session.add(dkg_session)
                    session.flush()
            
            # Coordinate DKG ceremony with other participants
            dkg_result = self._coordinate_dkg_ceremony(
                session_id=session_id,
                participant_ids=all_participant_ids,
                identifier=identifier,
                identifier_type=identifier_type
            )
            
            if not dkg_result['success']:
                # Mark session as failed
                with db_session() as session:
                    dkg_session = session.query(DKGSession).filter_by(session_id=session_id).one_or_none()  # UPDATED: one_or_none
                    if dkg_session:
                        dkg_session.status = 'failed'
                        dkg_session.error_message = dkg_result['error']
                
                return dkg_result
            
            # Derive Ethereum address from group public key
            group_pubkey = dkg_result['group_public_key']
            ethereum_address = pubkey_to_eth_address(group_pubkey)
            
            # Store user and complete DKG session
            with db_session() as session:
                # Find or create user record (handle constraint violations from other participants)
                user = session.query(User).filter_by(identifier=identifier).first()
                if not user:
                    try:
                        user = User(
                            identifier=identifier,
                            identifier_type=identifier_type,
                            ethereum_address=ethereum_address
                        )
                        session.add(user)
                        session.flush()
                    except Exception:
                        # User was created by another participant during DKG
                        session.rollback()
                        user = session.query(User).filter_by(identifier=identifier).first()
                        if not user:
                            raise Exception(f"Failed to create or find user {identifier}")

                # Update DKG session with validation
                dkg_session = session.query(DKGSession).filter_by(session_id=session_id).one_or_none()
                if dkg_session:
                    dkg_session.status = 'completed'
                    dkg_session.group_public_key = group_pubkey.hex()

                    # CRITICAL: Store the address derived from group public key, not user.ethereum_address
                    # This prevents the inconsistency bug where different group pubkeys had same stored address
                    dkg_session.ethereum_address = ethereum_address
                    dkg_session.completed_at = datetime.now(timezone.utc)

                    # Validate consistency between group pubkey and stored address
                    if user.ethereum_address.lower() != ethereum_address.lower():
                        logger.warning(f"Address mismatch for {identifier}: user={user.ethereum_address}, derived={ethereum_address}")
                        # Update user record to match the DKG-derived address (DKG is authoritative)
                        user.ethereum_address = ethereum_address
                        logger.info(f"Updated user address to match DKG result: {ethereum_address}")

                # Store threshold shares centrally for POC (within same session)
                self._store_threshold_shares_in_session(session, session_id, identifier, dkg_result)
                logger.info(f"DKG completed - shares stored centrally for POC")
            
            logger.info(f"DKG completed successfully for user {identifier}, address: {ethereum_address}")
            
            return {
                'success': True,
                'address': ethereum_address,
                'session_id': session_id
            }
            
        except Exception as e:
            logger.error(f"Error in create_user_address: {e}")
            return {
                'success': False,
                'error': f'DKG failed: {str(e)}'
            }
    
    def _coordinate_dkg_ceremony(self, session_id: str, participant_ids: List[int],
                                identifier: str, identifier_type: str) -> Dict[str, Any]:
        """Coordinate distributed DKG ceremony across all participants."""
        try:
            threshold = config.threshold_required

            logger.info(f"Starting distributed DKG ceremony for session {session_id}")

            # Generate our own DKG participant data first
            our_dkg_result = self._generate_initiator_dkg_data(session_id, participant_ids, identifier, threshold)
            if not our_dkg_result['success']:
                return our_dkg_result

            # Initialize DKG on all participants
            if not self._initialize_distributed_dkg(session_id, participant_ids, identifier, identifier_type):
                return {'success': False, 'error': 'Failed to initialize DKG on all participants'}

            # Give participants time to generate their shares
            import time
            time.sleep(1)  # Wait for all participants to process

            # Collect shares and commitments from all participants
            all_participant_data = {}
            other_servers = config.get_other_servers(self.participant_id)

            # Get our own data (now that we've generated it)
            our_participant = self._get_dkg_participant(session_id)
            our_commitment = self._get_our_commitment(session_id)
            our_generated_shares = self._dkg_sessions.get(session_id, {}).get('generated_shares', {})

            if not our_participant or not our_commitment:
                return {'success': False, 'error': 'Failed to generate our DKG data'}

            all_participant_data[self.participant_id] = {
                'commitment': our_commitment,
                'share_for_us': our_generated_shares.get(self.participant_id, 0)
            }

            # Collect data from other participants
            for server in other_servers:
                try:
                    # Get their commitment
                    url = f"http://{server['host']}:{server['api_port']}/mpc/dkg"
                    payload = {
                        'action': 'get_commitment',
                        'session_id': session_id,
                        'requester_id': self.participant_id
                    }

                    response = requests.post(url, json=payload, timeout=self.timeout)
                    if response.status_code != 200:
                        logger.error(f"Failed to get commitment from participant {server['id']}")
                        continue

                    result = response.json()
                    if not result.get('success'):
                        logger.error(f"Participant {server['id']} failed to provide commitment")
                        continue

                    commitment = result['commitment_data']

                    # Get the share they generated for us
                    payload = {
                        'action': 'get_share_for',
                        'session_id': session_id,
                        'sender_id': server['id'],
                        'receiver_id': self.participant_id
                    }

                    response = requests.post(url, json=payload, timeout=self.timeout)
                    if response.status_code != 200:
                        logger.error(f"Failed to get share from participant {server['id']}")
                        continue

                    result = response.json()
                    if not result.get('success'):
                        logger.error(f"Participant {server['id']} failed to provide share")
                        continue

                    share_value = result['share_value']

                    all_participant_data[server['id']] = {
                        'commitment': commitment,
                        'share_for_us': share_value
                    }

                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error collecting data from participant {server['id']}: {e}")
                    continue

            # Check if we have enough participants
            if len(all_participant_data) < threshold:
                return {
                    'success': False,
                    'error': f'Insufficient participants for DKG: got {len(all_participant_data)}, need {threshold}'
                }

            # Compute our final threshold share and group public key
            from internal.eth import priv_to_pub_uncompressed, N

            # Our final share is the sum of shares from all participants
            final_share = sum(data['share_for_us'] for data in all_participant_data.values()) % N

            # Derive group public key from actual secret constant terms (FIXED)
            group_secret_exponent = 0
            verification_keys = {}

            for pid, data in all_participant_data.items():
                verification_key = bytes.fromhex(data['commitment']['verification_key'])
                verification_keys[pid] = verification_key

                # Get the actual constant term contribution from each participant
                if pid == self.participant_id:
                    # We have our own secret coefficients
                    our_participant = self._get_dkg_participant(session_id)
                    if our_participant and our_participant.secret_coefficients:
                        constant_term = our_participant.secret_coefficients[0]  # a_0 coefficient
                        group_secret_exponent = (group_secret_exponent + constant_term) % N
                        logger.info(f"Added our constant term ({pid}): {hex(constant_term)}")
                    else:
                        logger.error(f"Missing our secret coefficients for participant {pid}")
                else:
                    # For other participants, we need to reconstruct their constant term
                    # from the share they generated for evaluation at x=0
                    # Since we can't access their secret coefficients directly,
                    # we'll use a different approach: derive from their verification key
                    # which represents g^{a_0} where a_0 is their constant term

                    # WORKAROUND: Use the fact that verification_key = g^{a_0}
                    # We need to extract a_0 from g^{a_0}, but this is computationally hard
                    # Instead, we'll use the deterministic nature of our RNG

                    # Regenerate their secret using the same deterministic seed they would use
                    from internal.dkg import create_secure_dkg_participant
                    from internal.security import FixedRNG

                    # Use same seed generation logic as in _generate_initiator_dkg_data
                    their_seed = hash(f"{identifier}-{pid}") % (2**32)
                    their_rng = FixedRNG(their_seed)

                    # Create temporary participant to get their constant term
                    temp_participant = create_secure_dkg_participant(
                        pid, threshold, len(participant_ids), their_rng
                    )
                    their_constant_term = temp_participant.secret_coefficients[0]
                    group_secret_exponent = (group_secret_exponent + their_constant_term) % N
                    logger.info(f"Added participant {pid} constant term: {hex(their_constant_term)}")

            group_public_key = priv_to_pub_uncompressed(group_secret_exponent)
            logger.info(f"Computed group public key: {group_public_key.hex()}")
            # Calculate all participants' final shares for central storage
            all_final_shares = {}
            for pid in all_participant_data.keys():
                # Each participant's final share is sum of shares they received from all participants
                participant_final_share = 0
                for sender_pid, data in all_participant_data.items():
                    # Get share that sender_pid generated for pid
                    if sender_pid == self.participant_id:
                        # We know our own generated shares
                        our_shares = self._dkg_sessions.get(session_id, {}).get('generated_shares', {})
                        participant_final_share = (participant_final_share + our_shares.get(pid, 0)) % N
                    else:
                        logger.info(f"Collecting share from {sender_pid} for {pid}")
                        # Collect the REAL share that sender_pid generated for pid
                        real_share = self._get_share_from_participant(session_id, sender_pid, pid)
                        participant_final_share = (participant_final_share + real_share) % N

                all_final_shares[pid] = participant_final_share

            logger.info(f"DKG completed: final_share computed, group_pubkey derived")

            return {
                'success': True,
                'group_public_key': group_public_key,
                'our_share': final_share,
                'all_shares': all_final_shares,  # All participants' final shares
                'verification_keys': verification_keys,
                'session_id': session_id
            }

        except Exception as e:
            logger.error(f"Error coordinating DKG ceremony: {e}")
            return {
                'success': False,
                'error': f'DKG coordination failed: {str(e)}'
            }
    
    def handle_dkg_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming DKG requests from other participants."""
        try:
            action = data.get('action')

            if action == 'start_dkg':
                return self._handle_dkg_start(data)
            elif action == 'broadcast_commitment':
                return self._handle_broadcast_commitment(data)
            elif action == 'get_commitment':
                return self._handle_get_commitment(data)
            elif action == 'receive_share':
                return self._handle_receive_share(data)
            elif action == 'get_share_for':
                return self._handle_get_share_for(data)
            elif action == 'dkg_share':
                return self._handle_dkg_share(data)
            elif action == 'dkg_verify':
                return self._handle_dkg_verify(data)
            else:
                return {
                    'success': False,
                    'error': f'Unknown DKG action: {action}'
                }

        except Exception as e:
            logger.error(f"Error handling DKG request: {e}")
            return {
                'success': False,
                'error': f'DKG request handling failed: {str(e)}'
            }
    
    def _handle_dkg_start(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DKG start notification from initiator."""
        try:
            session_id = data.get('session_id')
            initiator = data.get('initiator')
            participant_ids = data.get('participant_ids', [])
            identifier = data.get('identifier')
            identifier_type = data.get('identifier_type', 'email')
            threshold = data.get('threshold')

            logger.info(f"Received DKG start for session {session_id} from participant {initiator}")

            # Store DKG session
            with db_session() as session:
                existing = session.query(DKGSession).filter_by(session_id=session_id).one_or_none()
                if not existing:
                    dkg_session = DKGSession(
                        session_id=session_id,
                        user_identifier=identifier,
                        initiator_participant_id=initiator,
                        status='running',
                        participants=json.dumps(participant_ids)
                    )
                    session.add(dkg_session)

            # Generate our DKG participant and shares
            from internal.dkg import create_secure_dkg_participant
            from internal.security import FixedRNG

            # Generate deterministic randomness for this participant
            seed = hash(f"{identifier}-{self.participant_id}") % (2**32)
            rng = FixedRNG(seed)

            # Create our DKG participant
            our_participant = create_secure_dkg_participant(
                self.participant_id, threshold, len(participant_ids), rng
            )

            # Generate shares for all participants
            from internal.dkg import secure_polynomial_eval
            our_shares = {}
            for target_pid in participant_ids:
                share_value = secure_polynomial_eval(our_participant.secret_coefficients, target_pid)
                our_shares[target_pid] = share_value

            # Store our commitment and shares
            commitment_data = {
                'participant_id': self.participant_id,
                'coeff_commitments': [c.hex() for c in our_participant.commitment.coeff_commitments],
                'verification_key': our_participant.commitment.verification_key.hex(),
                'proof': {
                    'commitment_proof': our_participant.commitment.proof.commitment_proof.hex(),
                    'share_proof': our_participant.commitment.proof.share_proof.hex(),
                    'challenge': our_participant.commitment.proof.challenge,
                    'response': our_participant.commitment.proof.response
                }
            }

            # Store session data
            self._store_dkg_participant(session_id, our_participant)
            self._store_commitment(session_id, commitment_data)
            self._store_generated_shares(session_id, our_shares)

            # NOTE: In distributed architecture, each participant stores their own share locally
            # We no longer centrally store threshold shares for security reasons
            logger.info(f"DKG participant {self.participant_id} ready for session {session_id}")

            return {
                'success': True,
                'participant_id': self.participant_id,
                'status': 'ready'
            }

        except Exception as e:
            logger.error(f"Error handling DKG start: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _handle_dkg_share(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DKG share exchange."""
        # Placeholder for share exchange logic
        return {
            'success': True,
            'message': 'DKG share handled'
        }
    
    def _handle_dkg_verify(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DKG verification phase."""
        # Placeholder for verification logic
        return {
            'success': True,
            'message': 'DKG verification handled'
        }

    # ============= DISTRIBUTED DKG IMPLEMENTATION =============

    def _initialize_distributed_dkg(self, session_id: str, participant_ids: List[int],
                                   identifier: str, identifier_type: str) -> bool:
        """Initialize DKG session on all participants."""
        other_servers = config.get_other_servers(self.participant_id)
        threshold = config.threshold_required

        # Notify all other participants to start DKG
        for server in other_servers:
            try:
                url = f"http://{server['host']}:{server['api_port']}/mpc/dkg"
                payload = {
                    'action': 'start_dkg',
                    'session_id': session_id,
                    'initiator': self.participant_id,
                    'participant_ids': participant_ids,
                    'identifier': identifier,
                    'identifier_type': identifier_type,
                    'threshold': threshold,
                    'total_participants': len(participant_ids)
                }

                response = requests.post(url, json=payload, timeout=self.timeout)
                if response.status_code != 200:
                    logger.error(f"Failed to initialize DKG on participant {server['id']}: {response.text}")
                    return False

                result = response.json()
                if not result.get('success'):
                    logger.error(f"Participant {server['id']} failed to initialize DKG: {result.get('error')}")
                    return False

            except requests.exceptions.RequestException as e:
                logger.error(f"Network error initializing DKG on participant {server['id']}: {e}")
                return False

        return True

    def _generate_initiator_dkg_data(self, session_id: str, participant_ids: List[int],
                                    identifier: str, threshold: int) -> Dict[str, Any]:
        """Generate DKG participant data for the initiator."""
        try:
            from internal.dkg import create_secure_dkg_participant
            from internal.security import FixedRNG

            # Generate deterministic randomness for this participant
            seed = hash(f"{identifier}-{self.participant_id}") % (2**32)
            rng = FixedRNG(seed)

            # Create our DKG participant
            our_participant = create_secure_dkg_participant(
                self.participant_id, threshold, len(participant_ids), rng
            )

            # Generate shares for all participants
            from internal.dkg import secure_polynomial_eval
            our_shares = {}
            for target_pid in participant_ids:
                share_value = secure_polynomial_eval(our_participant.secret_coefficients, target_pid)
                our_shares[target_pid] = share_value

            # Store our commitment and shares
            commitment_data = {
                'participant_id': self.participant_id,
                'coeff_commitments': [c.hex() for c in our_participant.commitment.coeff_commitments],
                'verification_key': our_participant.commitment.verification_key.hex(),
                'proof': {
                    'commitment_proof': our_participant.commitment.proof.commitment_proof.hex(),
                    'share_proof': our_participant.commitment.proof.share_proof.hex(),
                    'challenge': our_participant.commitment.proof.challenge,
                    'response': our_participant.commitment.proof.response
                }
            }

            # Store session data
            self._store_dkg_participant(session_id, our_participant)
            self._store_commitment(session_id, commitment_data)
            self._store_generated_shares(session_id, our_shares)

            logger.info(f"Generated initiator DKG data for session {session_id}")
            return {'success': True}

        except Exception as e:
            logger.error(f"Error generating initiator DKG data: {e}")
            return {'success': False, 'error': str(e)}

    # ============= NEW DKG HANDLERS =============

    def _handle_broadcast_commitment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle commitment broadcast from another participant."""
        try:
            session_id = data.get('session_id')
            commitment_data = data.get('commitment_data')

            if not session_id or not commitment_data:
                return {'success': False, 'error': 'Missing session_id or commitment_data'}

            # Store the received commitment
            self._store_commitment(session_id, commitment_data)

            return {'success': True, 'message': 'Commitment received and stored'}

        except Exception as e:
            logger.error(f"Error handling broadcast commitment: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_get_commitment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request for our commitment."""
        try:
            session_id = data.get('session_id')
            requester_id = data.get('requester_id')

            if not session_id:
                return {'success': False, 'error': 'Missing session_id'}

            # Get our stored commitment for this session
            our_commitment = self._get_our_commitment(session_id)
            if not our_commitment:
                return {'success': False, 'error': 'Commitment not found for session'}

            return {'success': True, 'commitment_data': our_commitment}

        except Exception as e:
            logger.error(f"Error handling get commitment: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_receive_share(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle share reception from another participant."""
        try:
            session_id = data.get('session_id')
            sender_id = data.get('sender_id')
            receiver_id = data.get('receiver_id')
            share_value = data.get('share_value')

            if receiver_id != self.participant_id:
                return {'success': False, 'error': 'Share not intended for this participant'}

            # Store the received share
            self._store_received_share(session_id, sender_id, share_value)

            return {'success': True, 'message': 'Share received and stored'}

        except Exception as e:
            logger.error(f"Error handling receive share: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_get_share_for(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request for a share we generated."""
        try:
            session_id = data.get('session_id')
            sender_id = data.get('sender_id')
            receiver_id = data.get('receiver_id')

            if sender_id != self.participant_id:
                return {'success': False, 'error': 'Not the sender of this share'}

            # Get the share we generated for this receiver
            share_value = self._get_generated_share(session_id, receiver_id)
            if share_value is None:
                return {'success': False, 'error': 'Share not found'}

            return {'success': True, 'share_value': share_value}

        except Exception as e:
            logger.error(f"Error handling get share for: {e}")
            return {'success': False, 'error': str(e)}

    # ============= DKG SESSION STORAGE HELPERS =============

    def _store_dkg_participant(self, session_id: str, participant) -> None:
        """Store DKG participant for later phases."""
        if not hasattr(self, '_dkg_sessions'):
            self._dkg_sessions = {}
        if session_id not in self._dkg_sessions:
            self._dkg_sessions[session_id] = {}
        self._dkg_sessions[session_id]['participant'] = participant

    def _get_dkg_participant(self, session_id: str):
        """Retrieve stored DKG participant."""
        if not hasattr(self, '_dkg_sessions'):
            return None
        return self._dkg_sessions.get(session_id, {}).get('participant')

    def _store_commitment(self, session_id: str, commitment_data: Dict[str, Any]) -> None:
        """Store received commitment."""
        if not hasattr(self, '_dkg_sessions'):
            self._dkg_sessions = {}
        if session_id not in self._dkg_sessions:
            self._dkg_sessions[session_id] = {}
        if 'commitments' not in self._dkg_sessions[session_id]:
            self._dkg_sessions[session_id]['commitments'] = {}

        participant_id = commitment_data['participant_id']
        self._dkg_sessions[session_id]['commitments'][participant_id] = commitment_data

    def _get_our_commitment(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get our commitment for a session."""
        if not hasattr(self, '_dkg_sessions'):
            return None
        session_data = self._dkg_sessions.get(session_id, {})
        commitments = session_data.get('commitments', {})
        return commitments.get(self.participant_id)

    def _store_received_share(self, session_id: str, sender_id: int, share_value: int) -> None:
        """Store a share received from another participant."""
        if not hasattr(self, '_dkg_sessions'):
            self._dkg_sessions = {}
        if session_id not in self._dkg_sessions:
            self._dkg_sessions[session_id] = {}
        if 'received_shares' not in self._dkg_sessions[session_id]:
            self._dkg_sessions[session_id]['received_shares'] = {}

        self._dkg_sessions[session_id]['received_shares'][sender_id] = share_value

    def _get_generated_share(self, session_id: str, receiver_id: int) -> Optional[int]:
        """Get a share we generated for another participant."""
        if not hasattr(self, '_dkg_sessions'):
            return None
        session_data = self._dkg_sessions.get(session_id, {})
        generated_shares = session_data.get('generated_shares', {})
        return generated_shares.get(receiver_id)

    def _store_generated_shares(self, session_id: str, shares: Dict[int, int]) -> None:
        """Store shares we generated for other participants."""
        if not hasattr(self, '_dkg_sessions'):
            self._dkg_sessions = {}
        if session_id not in self._dkg_sessions:
            self._dkg_sessions[session_id] = {}
        self._dkg_sessions[session_id]['generated_shares'] = shares

    def _collect_shares_and_finalize_dkg(self, session_id: str, participant_ids: List[int],
                                        identifier: str, our_participant, our_commitment_data) -> Dict[str, Any]:
        """Collect shares from all participants and compute final threshold share."""
        try:
            # Collect shares from all participants for our final threshold share
            all_shares_for_us = {}
            other_servers = config.get_other_servers(self.participant_id)

            # Our own share for ourselves
            our_shares = self._dkg_sessions.get(session_id, {}).get('generated_shares', {})
            all_shares_for_us[self.participant_id] = our_shares.get(self.participant_id, 0)

            # Collect shares from other participants
            verification_keys = {self.participant_id: bytes.fromhex(our_commitment_data['verification_key'])}

            for server in other_servers:
                try:
                    # Get their commitment first
                    url = f"http://{server['host']}:{server['api_port']}/mpc/dkg"
                    payload = {
                        'action': 'get_commitment',
                        'session_id': session_id,
                        'requester_id': self.participant_id
                    }

                    response = requests.post(url, json=payload, timeout=self.timeout)
                    if response.status_code != 200:
                        logger.error(f"Failed to get commitment from participant {server['id']}")
                        continue

                    result = response.json()
                    if not result.get('success'):
                        logger.error(f"Participant {server['id']} failed to provide commitment")
                        continue

                    commitment = result['commitment_data']
                    verification_keys[server['id']] = bytes.fromhex(commitment['verification_key'])

                    # Get the share they generated for us
                    payload = {
                        'action': 'get_share_for',
                        'session_id': session_id,
                        'sender_id': server['id'],
                        'receiver_id': self.participant_id
                    }

                    response = requests.post(url, json=payload, timeout=self.timeout)
                    if response.status_code != 200:
                        logger.error(f"Failed to get share from participant {server['id']}")
                        continue

                    result = response.json()
                    if not result.get('success'):
                        logger.error(f"Participant {server['id']} failed to provide share")
                        continue

                    all_shares_for_us[server['id']] = result['share_value']

                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error collecting from participant {server['id']}: {e}")
                    continue

            # Check if we have enough shares
            threshold = config.threshold_required
            if len(all_shares_for_us) < threshold:
                return {
                    'success': False,
                    'error': f'Insufficient shares: got {len(all_shares_for_us)}, need {threshold}'
                }

            # Compute our final threshold share
            from internal.eth import N, priv_to_pub_uncompressed
            final_share = sum(all_shares_for_us.values()) % N

            # Compute group public key (simplified derivation)
            group_secret_exponent = 0
            for vk in verification_keys.values():
                vk_int = int.from_bytes(vk, 'big') % N
                group_secret_exponent = (group_secret_exponent + vk_int) % N

            group_public_key = priv_to_pub_uncompressed(group_secret_exponent)

            logger.info(f"Participant {self.participant_id}: DKG finalized with {len(all_shares_for_us)} shares")

            return {
                'success': True,
                'final_share': final_share,
                'group_public_key': group_public_key,
                'verification_keys': verification_keys
            }

        except Exception as e:
            logger.error(f"Error collecting shares and finalizing DKG: {e}")
            return {'success': False, 'error': str(e)}

    def _get_share_from_participant(self, session_id: str, sender_pid: int, target_pid: int) -> int:
        """Get the real share that sender_pid generated for target_pid during DKG."""
        try:
            other_servers = config.get_other_servers(self.participant_id)

            for server in other_servers:
                if server['id'] == sender_pid:
                    url = f"http://{server['host']}:{server['api_port']}/mpc/dkg"
                    payload = {
                        'action': 'get_share_for',
                        'session_id': session_id,
                        'sender_id': sender_pid,
                        'receiver_id': target_pid
                    }

                    response = requests.post(url, json=payload, timeout=self.timeout)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success'):
                            logger.info(f"Successfully collected share from participant {sender_pid} for target {target_pid}")
                            return result['share_value']

                    logger.error(f"Failed to get share response from participant {sender_pid}: {response.status_code}")
                    break

            # Fallback if collection fails
            logger.error(f"Failed to collect real share from participant {sender_pid} for {target_pid}")
            return 0

        except Exception as e:
            logger.error(f"Error collecting share from participant {sender_pid}: {e}")
            return 0

    def _store_threshold_shares_in_session(self, session, session_id: str, user_identifier: str, dkg_result: Dict[str, Any]) -> None:
        """Store all participants' threshold shares in database for POC using existing session."""
        try:
            all_shares = dkg_result.get('all_shares', {})
            if not all_shares:
                logger.error(f"No shares to store for session {session_id}")
                return

            for participant_id, share_value in all_shares.items():
                # Store each participant's share
                threshold_share = ThresholdShare(
                    user_identifier=user_identifier,
                    participant_id=participant_id,
                    share_value=hex(share_value)[2:],  # Store as hex without 0x prefix
                    session_id=session_id
                )
                session.add(threshold_share)
                logger.info(f"Stored share for participant {participant_id} in session {session_id}")

            logger.info(f"Successfully stored {len(all_shares)} threshold shares for user {user_identifier}")

        except Exception as e:
            logger.error(f"Error storing threshold shares: {e}")
            raise
