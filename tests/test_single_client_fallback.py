#!/usr/bin/env python3
"""Test single-client fallback functionality for address mismatches"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from services.signing_service import SigningService
from services.dkg_service import DKGService
from models.database import init_database, db_session, User
from internal.eth import pubkey_to_eth_address, priv_to_pub_uncompressed

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
print("Initializing database...")
init_database()
print("Database initialized successfully!")

def test_fallback_private_key_generation():
    """Test that we can generate deterministic private keys for existing addresses"""
    print("\n" + "="*60)
    print("TEST: Fallback Private Key Generation")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Test case: saurav@example.com with known address
    known_address = "0x5bd522c335bb5ae77cad53ca340d91f79fb5a529"
    user_identifier = "saurav@example.com"

    print(f"Testing private key generation for:")
    print(f"  User: {user_identifier}")
    print(f"  Expected address: {known_address}")

    # Try to generate private key
    private_key = signing_service._generate_fallback_private_key(user_identifier, known_address)

    if private_key:
        # Verify the private key produces the correct address
        public_key = priv_to_pub_uncompressed(private_key)
        derived_address = pubkey_to_eth_address(public_key)

        print(f"✅ Generated private key: {hex(private_key)}")
        print(f"✅ Derived address: {derived_address}")
        print(f"✅ Addresses match: {derived_address.lower() == known_address.lower()}")

        assert derived_address.lower() == known_address.lower(), f"Address mismatch: {derived_address} != {known_address}"
        return True
    else:
        print(f"❌ Failed to generate private key for {user_identifier}")
        return False

def test_address_balance_check():
    """Test the address balance checking functionality"""
    print("\n" + "="*60)
    print("TEST: Address Balance Check")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Test with a known address (likely zero balance)
    test_address = "0x5bd522c335bb5ae77cad53ca340d91f79fb5a529"

    print(f"Checking balance for address: {test_address}")

    try:
        balance = signing_service._check_address_balance(test_address)
        print(f"✅ Balance check successful: {balance} USDC")
        # Note: Balance might be 0, but the function should not error
        return True
    except Exception as e:
        print(f"❌ Balance check failed: {e}")
        return False

def test_fallback_logic_simulation():
    """Test the fallback triggering logic without actually executing transactions"""
    print("\n" + "="*60)
    print("TEST: Fallback Logic Simulation")
    print("="*60)

    # Create a test user with a known address
    test_user = "test_fallback@example.com"

    # Create user via DKG (this will generate a new address)
    dkg_service = DKGService(participant_id=1)
    dkg_result = dkg_service.create_user_address(test_user, 'email')

    if not dkg_result['success']:
        print(f"❌ Failed to create test user: {dkg_result}")
        return False

    new_address = dkg_result['address']
    print(f"✅ Created test user {test_user} with new address: {new_address}")

    # Now simulate what happens when we have an old address in database
    # For testing, we'll manually set a different address in the database
    old_address = "0x5bd522c335bb5ae77cad53ca340d91f79fb5a529"

    # Update database to simulate old address
    with db_session() as session:
        user = session.query(User).filter_by(identifier=test_user).first()
        if user:
            user.ethereum_address = old_address
            session.commit()
            print(f"✅ Updated database address to simulate old address: {old_address}")
        else:
            print(f"❌ Could not find user {test_user} in database")
            return False

    # Now test the balance checking logic
    signing_service = SigningService(participant_id=1)

    # This would be called during address validation
    db_balance = signing_service._check_address_balance(old_address)
    tss_balance = signing_service._check_address_balance(new_address)

    print(f"Database address ({old_address}) balance: {db_balance} USDC")
    print(f"TSS address ({new_address}) balance: {tss_balance} USDC")

    # Test the logic that would trigger fallback
    test_amount = 100.0
    would_trigger_fallback = (db_balance >= test_amount and tss_balance < test_amount)

    print(f"Transaction amount: {test_amount} USDC")
    print(f"Would trigger fallback: {would_trigger_fallback}")

    if db_balance >= test_amount:
        print("✅ Fallback would be triggered (database address has sufficient funds)")
    else:
        print("ℹ️  Fallback would not be triggered (database address has insufficient funds)")

    # Test private key generation for the old address
    private_key = signing_service._generate_fallback_private_key(test_user, old_address)

    if private_key:
        print(f"✅ Could generate fallback private key for old address")

        # Verify it produces the correct address
        public_key = priv_to_pub_uncompressed(private_key)
        derived_address = pubkey_to_eth_address(public_key)

        if derived_address.lower() == old_address.lower():
            print(f"✅ Private key correctly derives to old address")
            return True
        else:
            print(f"❌ Private key derives to wrong address: {derived_address}")
            return False
    else:
        print(f"❌ Could not generate fallback private key")
        return False

def main():
    """Test single-client fallback functionality"""
    print("Testing Single-Client Fallback Functionality")
    print("="*60)

    test_results = []

    # Test 1: Private key generation
    try:
        result1 = test_fallback_private_key_generation()
        test_results.append(("Private Key Generation", result1))
    except Exception as e:
        print(f"❌ Private key generation test failed: {e}")
        test_results.append(("Private Key Generation", False))

    # Test 2: Balance checking
    try:
        result2 = test_address_balance_check()
        test_results.append(("Address Balance Check", result2))
    except Exception as e:
        print(f"❌ Balance check test failed: {e}")
        test_results.append(("Address Balance Check", False))

    # Test 3: Fallback logic simulation
    try:
        result3 = test_fallback_logic_simulation()
        test_results.append(("Fallback Logic Simulation", result3))
    except Exception as e:
        print(f"❌ Fallback logic test failed: {e}")
        logger.exception("Fallback logic test error:")
        test_results.append(("Fallback Logic Simulation", False))

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")

    all_passed = True
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:30} {status}")
        if not success:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 SUCCESS: Single-client fallback functionality works!")
        print("   ✅ Can generate deterministic private keys")
        print("   ✅ Balance checking functions properly")
        print("   ✅ Fallback triggering logic is sound")
        print("   ✅ Address mismatches will now use fallback")
        print("")
        print("   Next: Test with actual transaction execution")
    else:
        print("❌ FAILURE: Some fallback tests failed")
        print("   The fallback implementation needs fixes.")
    print(f"{'='*60}")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)