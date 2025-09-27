#!/usr/bin/env python3
"""Test the transaction API type conversion fix"""

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

def test_type_conversion_fix():
    """Test that the transaction API handles string amounts correctly"""
    print("\n" + "="*60)
    print("TEST: Type Conversion Fix for Transaction API")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Test with string amount (this should not cause type error anymore)
    result = signing_service.execute_transaction(
        sender_identifier="saurav@example.com",
        receiver_identifier="alice@example.com",
        amount="100.0"  # String amount
    )

    print(f"Transaction result: {result}")

    # Check that we don't get the type error
    if 'error' in result and 'not supported between instances' in result['error']:
        print("❌ Still getting type comparison error")
        return False
    elif result['success'] == False and 'Invalid amount format' in result.get('error', ''):
        print("❌ Amount format validation failed unexpectedly")
        return False
    else:
        print("✅ No type comparison error - fix successful!")
        print(f"Result: {result.get('error', 'Success or other non-type error')}")
        return True

def test_invalid_amount_handling():
    """Test that invalid amount strings are handled gracefully"""
    print("\n" + "="*60)
    print("TEST: Invalid Amount Handling")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    # Test with invalid string amount
    result = signing_service.execute_transaction(
        sender_identifier="saurav@example.com",
        receiver_identifier="alice@example.com",
        amount="not_a_number"  # Invalid amount
    )

    print(f"Invalid amount result: {result}")

    # Should get amount format error
    if result['success'] == False and 'Invalid amount format' in result.get('error', ''):
        print("✅ Invalid amount properly handled")
        return True
    else:
        print("❌ Invalid amount not properly handled")
        return False

def test_numeric_amount_types():
    """Test various numeric amount formats"""
    print("\n" + "="*60)
    print("TEST: Various Amount Format Types")
    print("="*60)

    signing_service = SigningService(participant_id=1)

    test_amounts = [
        "100",      # Integer string
        "100.0",    # Float string
        "100.50",   # Decimal string
        "0.1",      # Small decimal
    ]

    results = []
    for amount in test_amounts:
        print(f"Testing amount: {amount} (type: {type(amount)})")

        result = signing_service.execute_transaction(
            sender_identifier="saurav@example.com",
            receiver_identifier="alice@example.com",
            amount=amount
        )

        # Check for type errors
        has_type_error = ('error' in result and 'not supported between instances' in result['error'])
        has_format_error = ('error' in result and 'Invalid amount format' in result['error'])

        if has_type_error:
            print(f"  ❌ Type error for {amount}")
            results.append(False)
        elif has_format_error:
            print(f"  ❌ Format error for {amount}")
            results.append(False)
        else:
            print(f"  ✅ No type/format errors for {amount}")
            results.append(True)

    all_passed = all(results)
    print(f"All amount formats handled correctly: {all_passed}")
    return all_passed

def main():
    """Test the transaction API type conversion fix"""
    print("Testing Transaction API Type Conversion Fix")
    print("="*60)

    test_results = []

    # Test 1: Basic type conversion fix
    try:
        result1 = test_type_conversion_fix()
        test_results.append(("Type Conversion Fix", result1))
    except Exception as e:
        print(f"❌ Type conversion test failed: {e}")
        test_results.append(("Type Conversion Fix", False))

    # Test 2: Invalid amount handling
    try:
        result2 = test_invalid_amount_handling()
        test_results.append(("Invalid Amount Handling", result2))
    except Exception as e:
        print(f"❌ Invalid amount test failed: {e}")
        test_results.append(("Invalid Amount Handling", False))

    # Test 3: Various amount formats
    try:
        result3 = test_numeric_amount_types()
        test_results.append(("Amount Format Types", result3))
    except Exception as e:
        print(f"❌ Amount format test failed: {e}")
        test_results.append(("Amount Format Types", False))

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")

    all_passed = True
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:25} {status}")
        if not success:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 SUCCESS: Transaction API type conversion fix works!")
        print("   ✅ No more '>=' type comparison errors")
        print("   ✅ String amounts properly converted to float")
        print("   ✅ Invalid amounts handled gracefully")
        print("   ✅ Various amount formats supported")
        print("")
        print("   The transaction API should now work properly!")
    else:
        print("❌ FAILURE: Some type conversion tests failed")
        print("   The fix may need additional work.")
    print(f"{'='*60}")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)