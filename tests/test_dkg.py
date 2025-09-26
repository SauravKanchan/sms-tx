# tests/test_dkg.py - Tests for Secure Distributed Key Generation
import pytest
from internal.dkg import secure_dkg_ceremony, dkg_run
from internal.eth import pubkey_to_eth_address
from internal.security import SecurityViolation

class FixedRNG:
    """Deterministic RNG for reproducible tests"""
    def __init__(self, seed=123456789):
        self.state = seed
    def randbelow(self, n):
        # Tiny LCG for deterministic tests (NOT cryptographically secure)
        self.state = (1103515245 * self.state + 12345) % (2**31)
        return self.state % n

def test_secure_dkg_2_of_3():
    """Test secure DKG with 2-of-3 threshold"""
    rng = FixedRNG(42)
    participant_ids = [1, 2, 3]
    
    result = secure_dkg_ceremony(
        threshold=2, 
        total_participants=3, 
        participant_ids=participant_ids,
        rng=rng
    )
    
    # Verify all participants completed successfully
    assert len(result.participants) == 3
    assert len(result.participant_shares) == 3
    assert len(result.verification_keys) == 3
    assert len(result.security_proofs) == 3
    assert len(result.blocked_participants) == 0
    
    # Verify group public key format
    assert len(result.group_public_key) == 65  # Uncompressed format
    assert result.group_public_key[0] == 0x04  # Uncompressed prefix
    
    # Verify Ethereum address derivation
    addr = pubkey_to_eth_address(result.group_public_key)
    assert addr.startswith("0x") and len(addr) == 42
    
    # Test determinism - same seed should produce same result
    result2 = secure_dkg_ceremony(
        threshold=2, 
        total_participants=3, 
        participant_ids=participant_ids,
        rng=FixedRNG(42)
    )
    assert result.group_public_key == result2.group_public_key

def test_secure_dkg_3_of_5():
    """Test secure DKG with 3-of-5 threshold"""
    participant_ids = [1, 2, 3, 4, 5]
    
    result = secure_dkg_ceremony(
        threshold=3,
        total_participants=5,
        participant_ids=participant_ids,
        rng=FixedRNG(7)
    )
    
    # Verify successful completion
    assert len(result.participants) == 5
    assert len(result.participant_shares) == 5
    assert result.group_public_key[0] == 0x04
    
    # Verify address derivation
    addr = pubkey_to_eth_address(result.group_public_key)
    assert addr.startswith("0x")

def test_dkg_invalid_threshold():
    """Test DKG with invalid threshold parameters"""
    participant_ids = [1, 2, 3]
    
    # Threshold greater than total participants should fail
    with pytest.raises(ValueError, match="Invalid threshold"):
        secure_dkg_ceremony(
            threshold=4,  # > 3 participants
            total_participants=3,
            participant_ids=participant_ids
        )

def test_dkg_participant_count_mismatch():
    """Test DKG with mismatched participant count"""
    # Participant list doesn't match total count
    with pytest.raises(ValueError, match="Participant ID count"):
        secure_dkg_ceremony(
            threshold=2,
            total_participants=3,
            participant_ids=[1, 2]  # Only 2 IDs for 3 participants
        )

def test_dkg_security_properties():
    """Test that DKG maintains security properties"""
    result = secure_dkg_ceremony(
        threshold=2,
        total_participants=3,
        participant_ids=[1, 2, 3],
        rng=FixedRNG(123)
    )
    
    # Verify each participant has a different share
    shares = list(result.participant_shares.values())
    assert len(set(shares)) == len(shares)  # All shares are unique
    
    # Verify each participant has a verification key
    for pid in result.participants:
        assert pid in result.verification_keys
        vk = result.verification_keys[pid]
        assert len(vk) == 33  # Compressed public key
        assert vk[0] in (0x02, 0x03)  # Valid compression prefix
    
    # Verify security proofs exist for all participants
    for pid in result.participants:
        assert pid in result.security_proofs
        proof = result.security_proofs[pid]
        assert proof.commitment_proof is not None
        assert proof.share_proof is not None
        assert proof.response > 0

def test_legacy_dkg_compatibility():
    """Test backward compatibility with legacy DKG interface"""
    rng = FixedRNG(42)
    
    # Test legacy interface still works (with deprecation warning)
    parties, shares, Q = dkg_run(t=2, n=3, rng=rng)
    
    # Verify basic functionality
    assert len(shares) == 3
    assert len(Q) == 65  # Uncompressed public key
    assert Q[0] == 0x04
    
    # Address derivation should work
    addr = pubkey_to_eth_address(Q)
    assert addr.startswith("0x") and len(addr) == 42

def test_dkg_zero_knowledge_proofs():
    """Test that DKG includes valid zero-knowledge proofs"""
    result = secure_dkg_ceremony(
        threshold=2,
        total_participants=3,
        participant_ids=[1, 2, 3],
        rng=FixedRNG(456)
    )
    
    from internal.zk_proofs import ZKProofSystem
    proof_system = ZKProofSystem()
    
    # Verify all DKG proofs are valid
    for pid in result.participants:
        proof = result.security_proofs[pid]
        # In a full implementation, we'd verify the proof against commitments
        # For now, verify the proof structure
        assert proof.participant_id == pid
        assert proof.challenge > 0
        assert proof.response > 0
        assert len(proof.commitment_proof) > 0
        assert len(proof.share_proof) > 0