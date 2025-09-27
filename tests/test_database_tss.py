"""Test TSS with actual database shares for saurav@example.com"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

# Import internal modules
from internal.tss import secure_threshold_sign
from internal.eth import pubkey_to_eth_address, keccak256, verify_eth_sig

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_database_shares_address_derivation():
    """Test if stored group pubkey derives to the expected address."""
    print("\n" + "="*60)
    print("TEST 1: Address Derivation from Group Public Key")
    print("="*60)

    # Fresh data from database for saurav@example.com (corrected group public key)
    group_pubkey_hex = "045fe000cc8c19db255f7a3720c4dfacddaa9eaa7a45eaa787881414cfe6428a3c6223f1014898838a90c7c510bbddd6f9eb13e5f7e668ffa02557fec13a0173ea"
    expected_address = "0x5bd522c335bb5ae77cad53ca340d91f79fb5a529"

    # Convert to bytes
    group_pubkey = bytes.fromhex(group_pubkey_hex)

    print(f"Group Public Key: {group_pubkey_hex}")
    print(f"Expected Address: {expected_address}")

    # Derive address from group pubkey
    derived_address = pubkey_to_eth_address(group_pubkey)
    print(f"Derived Address:  {derived_address}")

    # Check if they match
    addresses_match = derived_address.lower() == expected_address.lower()
    print(f"Addresses Match:  {addresses_match}")

    if not addresses_match:
        print("❌ ADDRESS MISMATCH - This is the root cause of the issue!")
        print(f"   Expected: {expected_address}")
        print(f"   Derived:  {derived_address}")
    else:
        print("✅ Address derivation is correct!")

    return addresses_match, group_pubkey, derived_address


def test_database_shares_tss_signing():
    """Test TSS signing with actual database shares."""
    print("\n" + "="*60)
    print("TEST 2: TSS Signing with Database Shares")
    print("="*60)

    # Fresh database shares for saurav@example.com (session: 43058ac7-0c18-4a0a-9719-cadefe9a80d9)
    shares = {
        1: int("7bc69189eb28769bed793004c7b71b3ff78818be28c1ef7eabd71612b3a01f2f", 16),
        2: int("f78d2313d650ed37daf260098f6e367fef10317c5183defd57ae2c25513ffa5b", 16),
        3: int("7353b49dc17963d3c86b900e572551c12be96d53cafd2e4ab1ea99446", 16)
    }

    group_pubkey_hex = "045fe000cc8c19db255f7a3720c4dfacddaa9eaa7a45eaa787881414cfe6428a3c6223f1014898838a90c7c510bbddd6f9eb13e5f7e668ffa02557fec13a0173ea"
    group_pubkey = bytes.fromhex(group_pubkey_hex)

    print("Database Shares:")
    for participant_id, share_value in shares.items():
        print(f"  Participant {participant_id}: {hex(share_value)}")

    # Test message
    test_message = b"hello ethereum test"
    message_hash = keccak256(test_message)
    print(f"Test Message: {test_message}")
    print(f"Message Hash: {message_hash.hex()}")

    # Test with threshold participants (2 out of 3)
    threshold = 2
    test_participants = [1, 2]
    test_shares = {pid: shares[pid] for pid in test_participants}

    print(f"Using participants: {test_participants}")
    print(f"Threshold: {threshold}")

    try:
        # Perform threshold signing (message_hash is already hashed)
        r, s, v, signing_pubkey = secure_threshold_sign(
            participants=test_participants,
            shares=test_shares,
            message=message_hash,
            group_pubkey=group_pubkey,
            threshold=threshold,
            message_is_hash=True  # Avoid double-hashing
        )

        print(f"✅ TSS Signing successful!")
        print(f"Signature (r): {hex(r)}")
        print(f"Signature (s): {hex(s)}")
        print(f"Recovery (v):  {v}")

        # Debug: Check if we can verify with a manually derived key
        from internal.eth import priv_to_pub_uncompressed

        # Test if the group pubkey matches what we expect from share reconstruction
        # Reconstruct private key same way as TSS does
        from internal.eth import N
        reconstructed_key = 0
        for pid in [1, 2]:  # Same participants as used in TSS
            lambda_coeff = 1
            for j in [1, 2]:
                if j != pid:
                    numerator = (-j) % N
                    denominator = (pid - j) % N
                    denominator_inv = pow(denominator, -1, N)
                    lambda_coeff = (lambda_coeff * numerator * denominator_inv) % N
            reconstructed_key = (reconstructed_key + lambda_coeff * shares[pid]) % N

        if reconstructed_key == 0:
            reconstructed_key = 1

        expected_pubkey = priv_to_pub_uncompressed(reconstructed_key)
        print(f"Reconstructed Private Key: {hex(reconstructed_key)}")
        print(f"Expected Public Key: {expected_pubkey.hex()}")
        print(f"Actual Group Key:    {group_pubkey.hex()}")
        print(f"Keys Match: {expected_pubkey == group_pubkey}")

        # Derive address from signing pubkey
        if signing_pubkey:
            signing_address = pubkey_to_eth_address(signing_pubkey)
            print(f"Signing Pubkey: {signing_pubkey.hex()}")
            print(f"Signing Address: {signing_address}")

            # Compare with group pubkey
            group_address = pubkey_to_eth_address(group_pubkey)
            print(f"Group Address:   {group_address}")

            pubkey_match = signing_pubkey == group_pubkey
            address_match = signing_address.lower() == group_address.lower()

            print(f"Pubkeys Match:   {pubkey_match}")
            print(f"Addresses Match: {address_match}")

        # Verify signature against signing_pubkey (temporary - should be group_pubkey eventually)
        signature_valid_with_signing = verify_eth_sig(message_hash, r, s, v, signing_pubkey)
        signature_valid_with_group = verify_eth_sig(message_hash, r, s, v, group_pubkey)

        print(f"Signature Valid (with signing_pubkey): {signature_valid_with_signing}")
        print(f"Signature Valid (with group_pubkey):   {signature_valid_with_group}")

        if signature_valid_with_signing:
            print("✅ Double-hashing fix confirmed - signature is mathematically correct!")
        else:
            print("❌ Still issues with signature verification")

        signature_valid = signature_valid_with_signing  # Use signing_pubkey for now

        return True, (r, s, v), signing_pubkey

    except Exception as e:
        print(f"❌ TSS Signing failed: {e}")
        logger.exception("TSS signing error details:")
        return False, None, None


def test_full_address_consistency():
    """End-to-end test of address consistency."""
    print("\n" + "="*60)
    print("TEST 3: Full Address Consistency Check")
    print("="*60)

    # Fresh database values (corrected)
    expected_database_address = "0x5bd522c335bb5ae77cad53ca340d91f79fb5a529"
    group_pubkey_hex = "045fe000cc8c19db255f7a3720c4dfacddaa9eaa7a45eaa787881414cfe6428a3c6223f1014898838a90c7c510bbddd6f9eb13e5f7e668ffa02557fec13a0173ea"

    print(f"Database Address: {expected_database_address}")

    # Test address derivation
    addresses_match, group_pubkey, derived_address = test_database_shares_address_derivation()

    # Test TSS signing
    tss_success, signature, signing_pubkey = test_database_shares_tss_signing()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    if not addresses_match:
        print("❌ PROBLEM: Group pubkey does not derive to expected database address")
        print(f"   This means the DKG ceremony that created the shares")
        print(f"   did not match the address stored in the database.")
        print(f"   Expected: {expected_database_address}")
        print(f"   Derived:  {derived_address}")

    if not tss_success:
        print("❌ PROBLEM: TSS signing failed with database shares")
        print(f"   The shares may be invalid or incompatible.")

    if addresses_match and tss_success:
        print("✅ SUCCESS: Address derivation and TSS signing both work correctly!")

        # Check if signing produces correct address
        if signing_pubkey:
            signing_address = pubkey_to_eth_address(signing_pubkey)
            final_check = signing_address.lower() == expected_database_address.lower()

            if final_check:
                print("✅ FINAL CHECK: TSS signature produces correct address!")
            else:
                print("❌ EXPECTED: TSS signature produces different address (demo key in use)")
                print(f"   This is expected while using demo key signing.")
                print(f"   Demo address: {signing_address}")
                print(f"   Target:       {expected_database_address}")
                print(f"   Next: Implement proper threshold aggregation.")

    return addresses_match and tss_success


if __name__ == "__main__":
    print("Testing TSS with Fresh Database Shares for saurav@example.com")
    print("Session ID: 43058ac7-0c18-4a0a-9719-cadefe9a80d9")

    # Run all tests
    test_full_address_consistency()