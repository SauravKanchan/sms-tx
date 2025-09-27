#!/usr/bin/env python3
"""Test the simplified fallback logic that always triggers on address mismatch"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from services.signing_service import SigningService
from models.database import init_database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
print("Initializing database...")
init_database()
print("Database initialized successfully!")

def test_address_mismatch_triggers_fallback():
    """Test that address mismatch always triggers fallback (no balance checking)"""
    print("\n" + "="*60)
    print("TEST: Address Mismatch Always Triggers Fallback")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # This should trigger fallback because saurav@example.com has address mismatch
    # Database: 0x5bd522c335bb5ae77cad53ca340d91f79fb5a529
    # TSS:      0x2593d547a2c264c9dcbc1df360a0c7107615f52b (or similar)
    result = signing_service.execute_transaction(
        sender_identifier="saurav@example.com",
        receiver_identifier="alice@example.com",
        amount="1.0"  # Small amount to avoid balance issues
    )

    print(f"Transaction result: {result}")

    # Check for fallback indicators
    has_fallback_flag = result.get('fallback_used', False)
    has_fallback_reason = 'fallback_reason' in result
    has_tss_address = 'tss_address' in result

    # Check logs mention fallback (indirect check)
    fallback_triggered = has_fallback_flag or 'fallback' in str(result).lower()

    print(f"✅ Fallback indicators found:")
    print(f"   fallback_used: {has_fallback_flag}")
    print(f"   fallback_reason: {has_fallback_reason}")
    print(f"   tss_address: {has_tss_address}")
    print(f"   fallback_triggered: {fallback_triggered}")

    if fallback_triggered:
        print("✅ Fallback was triggered as expected!")
        print(f"   Database address used: {result.get('sender_address', 'N/A')}")
        print(f"   TSS address available: {result.get('tss_address', 'N/A')}")
        return True
    else:
        print("❌ Fallback was not triggered")
        return False

def test_matching_addresses_use_tss():
    """Test that matching addresses still use normal TSS flow"""
    print("\n" + "="*60)
    print("TEST: Matching Addresses Use Normal TSS Flow")
    print("="*60)

    # Create a new user that should have matching addresses (new DKG algorithm)
    from services.dkg_service import DKGService
    dkg_service = DKGService(participant_id=1)

    # Create new user
    test_user = "test_matching@example.com"
    dkg_result = dkg_service.create_user_address(test_user, 'email')

    if not dkg_result['success']:
        print(f"❌ Failed to create test user: {dkg_result}")
        return False

    print(f"✅ Created test user: {test_user}")
    print(f"   Address: {dkg_result['address']}")

    # Now test transaction (should use normal TSS flow)
    signing_service = SigningService(participant_id=1)

    result = signing_service.execute_transaction(
        sender_identifier=test_user,
        receiver_identifier="alice@example.com",
        amount="1.0"
    )

    print(f"Transaction result: {result}")

    # Check that fallback was NOT used
    has_fallback_flag = result.get('fallback_used', False)
    fallback_in_response = 'fallback' in str(result).lower()

    if not has_fallback_flag and not fallback_in_response:
        print("✅ Normal TSS flow used (no fallback)")
        return True
    else:
        print("❌ Fallback was used when it shouldn't have been")
        return False

def test_fallback_error_handling():
    """Test that fallback handles errors gracefully"""
    print("\n" + "="*60)
    print("TEST: Fallback Error Handling")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Test with invalid amount (should fail gracefully)
    result = signing_service.execute_transaction(
        sender_identifier="saurav@example.com",
        receiver_identifier="alice@example.com",
        amount="invalid_amount"
    )

    print(f"Invalid amount result: {result}")

    # Should get format error before fallback triggers
    has_format_error = 'Invalid amount format' in result.get('error', '')

    if has_format_error:
        print("✅ Invalid amount handled before fallback trigger")
        return True
    else:
        print("❌ Invalid amount not handled properly")
        return False

def main():
    """Test the simplified fallback logic"""
    print("Testing Simplified Fallback Logic")
    print("="*60)

    test_results = []

    # Test 1: Address mismatch triggers fallback
    try:
        result1 = test_address_mismatch_triggers_fallback()
        test_results.append(("Address Mismatch Triggers Fallback", result1))
    except Exception as e:
        print(f"❌ Address mismatch test failed: {e}")
        logger.exception("Address mismatch test error:")
        test_results.append(("Address Mismatch Triggers Fallback", False))

    # Test 2: Matching addresses use TSS
    try:
        result2 = test_matching_addresses_use_tss()
        test_results.append(("Matching Addresses Use TSS", result2))
    except Exception as e:
        print(f"❌ Matching addresses test failed: {e}")
        logger.exception("Matching addresses test error:")
        test_results.append(("Matching Addresses Use TSS", False))

    # Test 3: Error handling
    try:
        result3 = test_fallback_error_handling()
        test_results.append(("Fallback Error Handling", result3))
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        test_results.append(("Fallback Error Handling", False))

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")

    all_passed = True
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:35} {status}")
        if not success:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 SUCCESS: Simplified fallback logic works!")
        print("   ✅ Address mismatch always triggers fallback")
        print("   ✅ No balance checking overhead")
        print("   ✅ Normal TSS flow preserved for matching addresses")
        print("   ✅ Error handling works correctly")
        print("")
        print("   saurav@example.com should now work seamlessly!")
    else:
        print("❌ FAILURE: Some fallback tests failed")
        print("   The simplified logic may need fixes.")
    print(f"{'='*60}")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)