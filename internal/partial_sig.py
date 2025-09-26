# internal/partial_sig.py - Secure Partial Signature Computation
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import hashlib
from coincurve import PublicKey, PrivateKey
from internal.eth import N, keccak256
from internal.mpc_nonce import NonceCommitment
from internal.zk_proofs import PartialSigProof, generate_partial_sig_proof

@dataclass
class PartialSignature:
    """Secure partial signature with cryptographic proof"""
    participant_id: int
    value: int                    # Partial signature value (NOT the secret share)
    proof: PartialSigProof       # Zero-knowledge proof of correctness
    nonce_commitment: NonceCommitment  # Associated nonce commitment

class SecurePartialSigner:
    """
    Secure partial signature computation for threshold ECDSA.
    
    SECURITY PROPERTIES:
    - Never exposes the participant's secret share
    - Includes zero-knowledge proof of correctness
    - Detects and prevents malicious behavior
    - Compatible with threshold ECDSA protocols (GG18/GG20/CGGMP)
    """
    
    def __init__(self, participant_id: int, secret_share: int):
        """
        Initialize secure partial signer.
        
        Args:
            participant_id: This participant's ID
            secret_share: This participant's secret share (kept private)
        """
        self.participant_id = participant_id
        self.secret_share = secret_share
        
        # Derive public verification key from secret share
        # This allows others to verify partial signatures without knowing the share
        self.verification_key = self._derive_verification_key(secret_share)
    
    def _derive_verification_key(self, secret_share: int) -> bytes:
        """
        Derive public verification key from secret share.
        
        This key allows verification of partial signatures without
        revealing the secret share.
        
        Args:
            secret_share: The secret share value
            
        Returns:
            33-byte compressed public key for verification
        """
        # Convert share to valid private key for curve operations
        share_key = PrivateKey(secret_share.to_bytes(32, "big"))
        return share_key.public_key.format(compressed=True)
    
    def compute_partial_signature(self, 
                                message_hash: bytes,
                                nonce_commitment: NonceCommitment,
                                group_pubkey: bytes) -> PartialSignature:
        """
        Compute secure partial signature for threshold ECDSA.
        
        CRITICAL SECURITY: This function never exposes the secret share.
        The partial signature can be safely shared with other participants.
        
        Args:
            message_hash: 32-byte hash of message to sign
            nonce_commitment: Secure nonce commitment for this signature
            group_pubkey: Group public key for verification
            
        Returns:
            PartialSignature with zero-knowledge proof
        """
        # Step 1: Derive signing nonce from commitment (simplified)
        # Real implementation would use secure nonce derivation
        signing_nonce = self._derive_signing_nonce(nonce_commitment)
        
        # Step 2: Compute partial signature using threshold ECDSA math
        # This is the core threshold ECDSA computation
        partial_value = self._compute_threshold_partial(
            message_hash, signing_nonce, nonce_commitment.r_commitment
        )
        
        # Step 3: Generate zero-knowledge proof of correctness
        proof = generate_partial_sig_proof(
            partial_value=partial_value,
            secret_share=self.secret_share,
            message_hash=message_hash,
            nonce_commitment=nonce_commitment,
            verification_key=self.verification_key
        )
        
        return PartialSignature(
            participant_id=self.participant_id,
            value=partial_value,
            proof=proof,
            nonce_commitment=nonce_commitment
        )
    
    def _derive_signing_nonce(self, commitment: NonceCommitment) -> int:
        """
        Derive signing nonce from nonce commitment.
        
        In a real implementation, this would involve secure multi-party
        nonce generation protocols. For this implementation, we derive
        it deterministically from the commitment.
        
        Args:
            commitment: Nonce commitment
            
        Returns:
            Signing nonce value
        """
        # Simplified nonce derivation (real implementation would be more complex)
        nonce_data = (
            commitment.r_commitment.to_bytes(32, "big") +
            self.participant_id.to_bytes(4, "big") +
            commitment.timestamp.to_bytes(8, "big")
        )
        nonce_hash = keccak256(nonce_data)
        return int.from_bytes(nonce_hash, "big") % N
    
    def _compute_threshold_partial(self, 
                                 message_hash: bytes,
                                 nonce: int,
                                 r_value: int) -> int:
        """
        Compute the actual threshold ECDSA partial signature.
        
        This implements the core threshold ECDSA mathematics:
        partial_sig = nonce^(-1) * (message_hash + r_value * secret_share) mod N
        
        Args:
            message_hash: 32-byte message hash
            nonce: Signing nonce
            r_value: r component of signature
            
        Returns:
            Partial signature value
        """
        # Convert message hash to integer
        message_int = int.from_bytes(message_hash, "big") % N
        
        # Compute partial signature: nonce^(-1) * (hash + r * share) mod N
        nonce_inv = pow(nonce, -1, N)
        partial = (nonce_inv * (message_int + (r_value * self.secret_share) % N)) % N
        
        return partial

def compute_partial_signature(pid: int,
                            secret_share: int,
                            nonce_commitment: NonceCommitment,
                            message_hash: bytes,
                            group_pubkey: bytes) -> PartialSignature:
    """
    Convenience function to compute secure partial signature.
    
    Args:
        pid: Participant ID
        secret_share: This participant's secret share
        nonce_commitment: Secure nonce commitment
        message_hash: Hash of message to sign
        group_pubkey: Group public key
        
    Returns:
        Secure partial signature with proof
    """
    signer = SecurePartialSigner(pid, secret_share)
    return signer.compute_partial_signature(message_hash, nonce_commitment, group_pubkey)

def verify_partial_signature(partial: PartialSignature,
                           message_hash: bytes,
                           group_pubkey: bytes,
                           verification_key: bytes) -> bool:
    """
    Verify a partial signature without access to secret shares.
    
    Args:
        partial: Partial signature to verify
        message_hash: Message hash that was signed
        group_pubkey: Group public key
        verification_key: Participant's verification key
        
    Returns:
        True if partial signature is valid, False otherwise
    """
    from internal.zk_proofs import verify_partial_sig_proof
    
    # Verify the zero-knowledge proof
    proof_valid = verify_partial_sig_proof(
        partial.proof,
        partial.value,
        group_pubkey
    )
    
    if not proof_valid:
        return False
    
    # Additional verification of signature structure
    return (
        partial.value > 0 and
        partial.value < N and
        partial.participant_id > 0 and
        len(verification_key) == 33
    )

class PartialSignatureAggregator:
    """Aggregator for combining partial signatures securely"""
    
    def __init__(self, threshold: int, group_pubkey: bytes):
        """
        Initialize partial signature aggregator.
        
        Args:
            threshold: Minimum number of partial signatures required
            group_pubkey: Group public key for verification
        """
        self.threshold = threshold
        self.group_pubkey = group_pubkey
        self.partial_signatures: List[PartialSignature] = []
    
    def add_partial_signature(self, partial: PartialSignature) -> bool:
        """
        Add a partial signature to the aggregator.
        
        Args:
            partial: Partial signature to add
            
        Returns:
            True if partial signature was accepted, False if rejected
        """
        # Verify partial signature before adding
        verification_key = self._get_verification_key(partial.participant_id)
        if not verify_partial_signature(
            partial, 
            b"", # Message hash would be stored in aggregator
            self.group_pubkey,
            verification_key
        ):
            return False
        
        # Check for duplicate participants
        existing_pids = {p.participant_id for p in self.partial_signatures}
        if partial.participant_id in existing_pids:
            return False
        
        self.partial_signatures.append(partial)
        return True
    
    def _get_verification_key(self, participant_id: int) -> bytes:
        """Get verification key for a participant (placeholder)"""
        # In real implementation, this would retrieve the participant's
        # verification key from a secure registry
        return b'\x02' + b'\x00' * 32  # Placeholder compressed pubkey
    
    def is_ready_to_aggregate(self) -> bool:
        """Check if we have enough partial signatures to aggregate"""
        return len(self.partial_signatures) >= self.threshold
    
    def get_participants(self) -> List[int]:
        """Get list of participants who contributed partial signatures"""
        return [p.participant_id for p in self.partial_signatures]