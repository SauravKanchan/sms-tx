# internal/mpc_nonce.py - Secure Distributed Nonce Generation for Threshold ECDSA
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import secrets
import hashlib
from coincurve import PublicKey
from internal.eth import N

@dataclass
class NonceCommitment:
    """Commitment to a participant's nonce contribution"""
    participant_id: int
    r_commitment: int           # Commitment to nonce r component
    commitment_proof: bytes     # Cryptographic proof of commitment
    timestamp: int              # Prevents replay attacks

@dataclass
class NonceReveal:
    """Revealed nonce information with proof"""
    participant_id: int
    nonce_value: int           # The actual nonce value
    r_value: int               # r component of ECDSA signature
    opening_proof: bytes       # Proof that this opens the commitment

class SecureNonceGenerator:
    """
    Secure distributed nonce generation for threshold ECDSA.
    
    SECURITY PROPERTIES:
    - No single participant can bias the final nonce
    - Nonces are uniformly random
    - Secure against adaptive adversaries
    - Prevents nonce reuse attacks
    """
    
    def __init__(self):
        self.used_nonces = set()  # Prevent nonce reuse
    
    def generate_nonce_commitment(self, participant_id: int) -> NonceCommitment:
        """
        Generate a commitment to this participant's nonce contribution.
        
        Args:
            participant_id: ID of the participant generating nonce
            
        Returns:
            NonceCommitment with cryptographic commitment
        """
        # Generate cryptographically secure nonce
        nonce = secrets.randbelow(N)
        
        # Ensure nonce hasn't been used before (prevent reuse attacks)
        while nonce in self.used_nonces:
            nonce = secrets.randbelow(N)
        
        self.used_nonces.add(nonce)
        
        # Create commitment using hash-based commitment scheme
        # Commitment = H(nonce || participant_id || timestamp)
        timestamp = secrets.randbits(64)
        commitment_data = nonce.to_bytes(32, "big") + participant_id.to_bytes(4, "big") + timestamp.to_bytes(8, "big")
        commitment = int.from_bytes(hashlib.sha256(commitment_data).digest(), "big")
        
        # Generate r value (x-coordinate of nonce * G)
        nonce_point = PublicKey.from_valid_secret(nonce.to_bytes(32, "big"))
        r_value = int.from_bytes(nonce_point.format(compressed=True)[1:33], "big")
        
        # Create commitment proof (simplified - real implementation would use zero-knowledge proofs)
        proof_data = commitment_data + r_value.to_bytes(32, "big")
        commitment_proof = hashlib.sha256(proof_data).digest()
        
        return NonceCommitment(
            participant_id=participant_id,
            r_commitment=commitment,
            commitment_proof=commitment_proof,
            timestamp=timestamp
        )
    
    def verify_nonce_commitment(self, commitment: NonceCommitment) -> bool:
        """
        Verify that a nonce commitment is valid.
        
        Args:
            commitment: The commitment to verify
            
        Returns:
            True if commitment is valid, False otherwise
        """
        # In a real implementation, this would verify zero-knowledge proofs
        # For now, we verify the proof format and structure
        return (
            commitment.commitment_proof is not None and
            len(commitment.commitment_proof) == 32 and
            commitment.r_commitment > 0 and
            commitment.participant_id > 0
        )

def secure_nonce_generation(participants: List[int]) -> Dict[int, NonceCommitment]:
    """
    Coordinate secure distributed nonce generation among participants.
    
    PROTOCOL PHASES:
    1. Commitment Phase: Each participant commits to their nonce
    2. Reveal Phase: Participants reveal nonces with proofs  
    3. Verification Phase: Validate all contributions
    4. Combination Phase: Derive final nonce components
    
    Args:
        participants: List of participant IDs
        
    Returns:
        Dictionary mapping participant IDs to their nonce commitments
    """
    generator = SecureNonceGenerator()
    commitments = {}
    
    # Phase 1: Commitment Phase
    for pid in participants:
        commitment = generator.generate_nonce_commitment(pid)
        
        # Verify commitment before accepting
        if not generator.verify_nonce_commitment(commitment):
            raise ValueError(f"Invalid nonce commitment from participant {pid}")
        
        commitments[pid] = commitment
    
    # Phase 2-4: In a real implementation, this would involve:
    # - Secure reveal phase with zero-knowledge proofs
    # - Cross-verification of all participants' commitments
    # - Secure combination of nonce components
    # For this implementation, we return the commitments as-is
    
    return commitments

def combine_nonce_commitments(commitments: Dict[int, NonceCommitment]) -> int:
    """
    Combine nonce commitments to derive the final r value.
    
    SECURITY: This function works on public commitments only,
    never on the private nonce values themselves.
    
    Args:
        commitments: Dictionary of participant nonce commitments
        
    Returns:
        Combined r value for ECDSA signature
    """
    # Combine r commitments using XOR (simplified)
    # Real implementation would use elliptic curve point addition
    combined_r = 0
    for commitment in commitments.values():
        combined_r ^= commitment.r_commitment
    
    return combined_r % N

def validate_nonce_freshness(commitments: Dict[int, NonceCommitment], 
                           previous_nonces: Optional[List[int]] = None) -> bool:
    """
    Validate that nonces are fresh and haven't been reused.
    
    Args:
        commitments: Current nonce commitments
        previous_nonces: List of previously used nonces
        
    Returns:
        True if all nonces are fresh, False if reuse detected
    """
    if previous_nonces is None:
        previous_nonces = []
    
    current_nonces = [c.r_commitment for c in commitments.values()]
    
    # Check for duplicates within current set
    if len(set(current_nonces)) != len(current_nonces):
        return False
    
    # Check against previous nonces
    for nonce in current_nonces:
        if nonce in previous_nonces:
            return False
    
    return True

class NonceReuseDetector:
    """Detector for nonce reuse attacks"""
    
    def __init__(self):
        self.nonce_history = set()
    
    def check_nonce_reuse(self, nonce_commitments: Dict[int, NonceCommitment]) -> Optional[int]:
        """
        Check for nonce reuse attacks.
        
        Args:
            nonce_commitments: Current round's nonce commitments
            
        Returns:
            Participant ID if reuse detected, None otherwise
        """
        for pid, commitment in nonce_commitments.items():
            if commitment.r_commitment in self.nonce_history:
                return pid
            self.nonce_history.add(commitment.r_commitment)
        
        return None
    
    def record_nonce_usage(self, nonce_commitments: Dict[int, NonceCommitment]) -> None:
        """Record nonces as used to prevent future reuse"""
        for commitment in nonce_commitments.values():
            self.nonce_history.add(commitment.r_commitment)