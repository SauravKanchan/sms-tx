#!/usr/bin/env python3
"""Test that error responses include sender_address for debugging"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from services.signing_service import SigningService
from models.database import init_database

# Set up logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise
logger = logging.getLogger(__name__)

# Initialize database
print("Initializing database...")
init_database()
print("Database initialized successfully!")

def test_sender_not_found_error():
    """Test that sender not found error includes sender_address field"""
    print("\n" + "="*60)
    print("TEST: Sender Not Found Error Response")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Try to execute transaction for non-existent user
    result = signing_service.execute_transaction(
        sender_identifier="nonexistent@example.com",
        receiver_identifier="alice@example.com",
        amount=100.0
    )

    print(f"Response: {result}")

    # Verify error response structure
    assert result['success'] == False, "Expected error response"
    assert 'sender_address' in result, "Missing sender_address in error response"
    assert result['sender_address'] is None, "Expected None for nonexistent user"
    assert 'note' in result, "Missing helpful note in error response"

    print("✅ Sender not found error includes sender_address: " + str(result['sender_address']))
    print("✅ Helpful note included: " + result['note'])
    return True

def test_insufficient_shares_error():
    """Test error when user exists but has no threshold shares"""
    print("\n" + "="*60)
    print("TEST: Insufficient Shares Error Response")
    print("="*60)

    # First create a user without setting up threshold shares
    from services.dkg_service import DKGService
    dkg_service = DKGService(participant_id=1)

    # Create user address
    result = dkg_service.create_user_address("testuser@example.com", 'email')
    if result['success']:
        print(f"✅ Created test user with address: {result['address']}")

        # Now clear threshold shares to simulate missing shares
        from models.database import db_session, ThresholdShare
        with db_session() as session:
            # Delete threshold shares for this user
            session.query(ThresholdShare).filter_by(user_identifier="testuser@example.com").delete()
            session.commit()
        print("✅ Cleared threshold shares to simulate error condition")

        # Try to execute transaction - should fail with shares error
        signing_service = SigningService(participant_id=1)

        # This should trigger a "no threshold shares found" error
        tx_result = signing_service.execute_transaction(
            sender_identifier="testuser@example.com",
            receiver_identifier="alice@example.com",
            amount=100.0
        )

        print(f"Response: {tx_result}")

        # Verify error response includes sender_address
        assert tx_result['success'] == False, "Expected error response"
        assert 'sender_address' in tx_result, "Missing sender_address in error response"
        assert tx_result['sender_address'] == result['address'], f"Expected sender_address to be {result['address']}"

        print(f"✅ Threshold shares error includes sender_address: {tx_result['sender_address']}")
        return True
    else:
        print(f"❌ Failed to create test user: {result}")
        return False

def main():
    """Test error response improvements"""
    print("Testing Error Response Improvements")
    print("="*60)

    test_results = []

    # Test 1: Sender not found
    try:
        result1 = test_sender_not_found_error()
        test_results.append(("Sender Not Found Error", result1))
    except Exception as e:
        print(f"❌ Sender not found test failed: {e}")
        test_results.append(("Sender Not Found Error", False))

    # Test 2: Insufficient shares
    try:
        result2 = test_insufficient_shares_error()
        test_results.append(("Insufficient Shares Error", result2))
    except Exception as e:
        print(f"❌ Insufficient shares test failed: {e}")
        test_results.append(("Insufficient Shares Error", False))

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
        print("🎉 SUCCESS: All error responses include sender_address!")
        print("   ✅ Transaction API errors now provide address context")
        print("   ✅ Debugging 'insufficient USDC' errors will be easier")
        print("   ✅ Error responses are comprehensive and helpful")
    else:
        print("❌ FAILURE: Some error responses still missing sender_address")
        print("   The error response improvements need more work.")
    print(f"{'='*60}")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)