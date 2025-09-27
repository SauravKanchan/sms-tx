#!/bin/bash

# MPC Signature Server API Test Script
# This script tests the main API endpoints

set -e

BASE_URL="http://localhost:3001"

echo "Testing MPC Signature Server API..."
echo "Base URL: $BASE_URL"
echo ""

# Test 1: Health check (ping)
echo "1. Testing health check endpoint..."
response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$BASE_URL/api/ping")
http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "200" ]; then
    echo "✅ Ping successful"
    echo "   Response: $body"
else
    echo "❌ Ping failed (HTTP $http_status)"
    echo "   Response: $body"
fi

echo ""

# Test 2: Server status
echo "2. Testing server status endpoint..."
response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$BASE_URL/api/status")
http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "200" ]; then
    echo "✅ Status check successful"
    echo "   Response: $body"
else
    echo "❌ Status check failed (HTTP $http_status)"
    echo "   Response: $body"
fi

echo ""

# Test 3: Create user address
echo "3. Testing address creation endpoint..."
test_email="test@example.com"
response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"identifier\":\"$test_email\",\"type\":\"email\"}" \
    "$BASE_URL/api/address")

http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "200" ]; then
    echo "✅ Address creation successful"
    echo "   Response: $body"
    
    # Extract address for transaction test
    address=$(echo "$body" | grep -o '"address":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$address" ]; then
        echo "   Created address: $address"
    fi
else
    echo "❌ Address creation failed (HTTP $http_status)"
    echo "   Response: $body"
fi

echo ""

# Test 4: Create second user for transaction test
echo "4. Creating second user for transaction test..."
test_email2="test2@example.com"
response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"identifier\":\"$test_email2\",\"type\":\"email\"}" \
    "$BASE_URL/api/address")

http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "200" ]; then
    echo "✅ Second user creation successful"
    echo "   Response: $body"
    
    address2=$(echo "$body" | grep -o '"address":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$address2" ]; then
        echo "   Created address: $address2"
    fi
else
    echo "❌ Second user creation failed (HTTP $http_status)"
    echo "   Response: $body"
fi

echo ""

# Test 5: Transaction (this will likely fail due to no USDC balance, but tests the endpoint)
echo "5. Testing transaction endpoint..."
response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"sender\":\"$test_email\",\"receiver\":\"$test_email2\",\"amount\":\"10.0\"}" \
    "$BASE_URL/api/transaction")

http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "200" ]; then
    echo "✅ Transaction successful"
    echo "   Response: $body"
else
    echo "⚠️  Transaction failed (expected - HTTP $http_status)"
    echo "   Response: $body"
    echo "   Note: This is expected if users don't have USDC balance"
fi

echo ""

# Test 6: Invalid request handling
echo "6. Testing error handling..."
response=$(curl -s -w "HTTP_STATUS:%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"invalid\":\"data\"}" \
    "$BASE_URL/api/address")

http_status=$(echo "$response" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
body=$(echo "$response" | sed -E 's/HTTP_STATUS:[0-9]*$//')

if [ "$http_status" = "400" ]; then
    echo "✅ Error handling working correctly"
    echo "   Response: $body"
else
    echo "❌ Error handling unexpected (HTTP $http_status)"
    echo "   Response: $body"
fi

echo ""
echo "API testing complete!"
echo ""
echo "Note: Some failures are expected if:"
echo "- Other servers (participants 2 & 3) are not running"
echo "- Blockchain connection issues"
echo "- No USDC balance for transactions"