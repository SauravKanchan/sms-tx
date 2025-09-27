![SmsTx Logo](logo.png)

# SmsTx - SMS-Only Crypto Wallet with Threshold Cryptography

An SMS-only crypto wallet where users transact by texting a single service number ("SEC"). A DKG → MPC-ECDSA backend creates and guards each user's secp256k1 key shares, so signatures are produced threshold-securely without ever reconstructing the private key. Works on any phone with SMS—no app, no internet—while staying Ethereum-compatible.

## 🔒 Short Description

A revolutionary cryptocurrency wallet that operates entirely through SMS messages, leveraging advanced threshold cryptography to eliminate single points of failure. Users can send, receive, and manage crypto assets using nothing more than text messages to a service number, with military-grade security powered by distributed key generation and multi-party computation.

## 📱 How It Works

Users interact with the wallet by sending plain texts to a common service number (SEC). On first contact, the platform runs a **t-of-n DKG ceremony** to generate a shared key for the sender's phone number; the key is split across independent nodes. Subsequent messages like **"send $10 to Himang"** trigger a **malicious-secure MPC-ECDSA signing flow**: nodes verify the command is authorized by the sender's number, jointly produce a valid `(r,s,v)` over secp256k1, and broadcast the transaction.

If the recipient (e.g., Himang) isn't onboarded yet, the system **auto-onboards** them by running DKG for their number before transferring, so value can be pushed to anyone reachable by SMS. The private key **never exists in one place**, eliminating a single point of compromise, while UX stays as simple as texting.

## ✨ Key Features

- 🔐 **Zero Single Point of Failure**: Private keys never exist in complete form anywhere
- 📱 **SMS-Only Interface**: Works on any phone with SMS capability - no app, no internet required
- 🚀 **Automatic Onboarding**: Recipients are automatically onboarded via DKG ceremonies
- 🔗 **Ethereum Compatible**: Full compatibility with Ethereum ecosystem and tooling
- 🛡️ **Production-Grade Security**: Implements advanced cryptographic protocols with malicious participant detection
- 📞 **Phone Number Validation**: Robust validation ensuring secure 10-digit Indian mobile number format
- 🌐 **Natural Language Processing**: AI-powered command interpretation for user-friendly interactions

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   SMS Messages  │───▶│  React Native    │───▶│  Python Backend     │
│   (User Input)  │    │  SMS Handler     │    │  (Threshold Crypto) │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                              │                           │
                              │                           ▼
                              │                 ┌─────────────────────┐
                              │                 │   AI Intent         │
                              │                 │   Processing        │
                              │                 └─────────────────────┘
                              │                           │
                              │                           ▼
                              │                 ┌─────────────────────┐
                              │                 │  Phone Number       │
                              │                 │  Validation         │
                              │                 └─────────────────────┘
                              │                           │
                              ▼                           ▼
                    ┌──────────────────┐    ┌─────────────────────┐
                    │  SMS Response    │◀───│  DKG & TSS Engine  │
                    │  (Transaction    │    │  (Threshold ECDSA)  │
                    │   Confirmation)  │    └─────────────────────┘
                    └──────────────────┘              │
                                                      ▼
                                            ┌─────────────────────┐
                                            │  Ethereum Network   │
                                            │  (Arbitrum Sepolia) │
                                            └─────────────────────┘
```

### Components:

1. **SMS Handler (React Native)**: Receives and sends SMS messages, handles permissions and device integration
2. **AI Intent Processing**: Natural language understanding to parse user commands
3. **Phone Validation**: Ensures secure 10-digit Indian mobile number format
4. **DKG & TSS Engine**: Implements secure distributed key generation and threshold signing
5. **Blockchain Interface**: Interacts with Ethereum-compatible networks

## 🔐 Cryptography

This project implements state-of-the-art threshold cryptography to ensure maximum security without sacrificing usability.

### Distributed Key Generation (DKG)

**Algorithm**: **Feldman VSS (Verifiable Secret Sharing)**

- **Purpose**: Generate shared secp256k1 private keys without any single party ever knowing the complete key
- **Security Model**: Assumes honest majority (>2/3) or threshold honest (≥t) depending on protocol phase
- **Implementation**:
  - Each party samples a degree `t-1` polynomial with secret coefficients
  - Commitments enable verification of shares without revealing secrets
  - VSS prevents malicious share distribution through cryptographic proofs
  - Group public key derived from commitments only

**Key Properties**:
- ✅ **No Secret Reconstruction**: Private key never materialized by any single participant
- ✅ **Verifiable**: All participants can verify the integrity of the DKG process
- ✅ **Malicious Security**: Detects and handles Byzantine participants
- ✅ **Zero-Knowledge Proofs**: All operations include correctness proofs

### Threshold Signature Scheme (TSS)

**Algorithm**: **GG18/GG20/CGGMP Protocols for Threshold ECDSA**

- **Purpose**: Generate valid ECDSA signatures over secp256k1 without reconstructing private keys
- **Security Model**: Provides security against adaptive adversaries and malicious participants
- **Implementation**:
  - **Phase 1**: Distributed nonce generation using secure MPC
  - **Phase 2**: Message preparation with `keccak256(msg)` → 32 bytes
  - **Phase 3**: Partial signature computation using only individual key shares
  - **Phase 4**: Secure aggregation with zero-knowledge proofs
  - **Phase 5**: Signature verification and Ethereum compatibility normalization

**Advanced Security Features**:
- 🛡️ **Malicious Participant Detection**: Identifies and excludes Byzantine actors
- 🔒 **Secure Nonce Generation**: Anti-bias properties prevent nonce manipulation
- 📊 **Zero-Knowledge Proofs**: Every operation includes cryptographic correctness proofs
- 🚨 **Abort Attack Prevention**: Handles and recovers from abort attacks
- ⚡ **Optimal Round Complexity**: Efficient communication patterns for production use

### Ethereum Compatibility

**Curve & Signatures**:
- **secp256k1** elliptic curve (same as Bitcoin/Ethereum)
- **ECDSA** signatures with Ethereum canonical **low-S** (EIP-2)
- Correct `(r, s, v)` format with recovery ID for `ecrecover` compatibility

**Hashing**:
- `keccak256(message)` → 32 bytes (Ethereum standard)
- Address derivation: last 20 bytes of `keccak(uncompressed_pubkey[1:])`

**Security Guarantees**:
- 🔐 **Secret Never Reconstructed**: TSS protocols maintain security throughout
- 🎯 **Threshold Security**: Any `t`-of-`n` participants can sign, `<t` cannot
- 🚫 **Single Point Elimination**: No individual node compromise affects security
- ✅ **Standard Compatibility**: Signatures indistinguishable from single-party ECDSA

## 🛠️ Technical Stack

### Backend (Python)
- **Framework**: Flask with CORS enabled
- **Cryptography**:
  - `coincurve` - secp256k1 operations & recovery
  - `eth-utils` - Keccak256 hashing
  - `eth-keys` - Ethereum key management
  - `pycryptodome` - Cryptographic primitives
- **Database**: SQLAlchemy
- **Blockchain**: Web3.py with Ethereum integration
- **AI Processing**: Custom ASI1 client for natural language understanding

### Frontend (React Native + Expo)
- **Framework**: Expo SDK ~54.0
- **SMS Handling**:
  - `react-native-get-sms-android` - SMS reception
  - `react-native-mobile-sms` - SMS sending
- **Background Processing**: `expo-background-task`, `expo-task-manager`
- **UI**: React Native with TypeScript

### Blockchain
- **Network**: Ethereum (Arbitrum Sepolia testnet)
- **Token**: PyUSD (for transactions)
- **Compatibility**: Full Ethereum ecosystem support

## 📁 Project Structure

```
sms-tx/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── server.py                   # Main Flask server
├── claude.md                  # Detailed implementation specs
│
├── internal/                   # Core cryptographic modules
│   ├── dkg.py                 # Feldman VSS DKG implementation
│   ├── tss.py                 # GG18/GG20/CGGMP threshold ECDSA
│   ├── mpc_nonce.py          # Distributed nonce generation
│   ├── partial_sig.py        # Partial signature computation
│   ├── zk_proofs.py          # Zero-knowledge proof system
│   ├── eth.py                # Ethereum compatibility layer
│   └── security.py           # Malicious participant detection
│
├── services/                   # Business logic services
│   ├── dkg_service.py         # DKG ceremony orchestration
│   ├── signing_service.py     # Threshold signing coordination
│   └── blockchain_service.py  # Ethereum network interface
│
├── utils/                      # Utility functions
│   ├── config.py              # Configuration management
│   ├── action_handlers.py     # Request routing logic
│   └── phone_validator.py     # Phone number validation
│
├── models/                     # Database models
│   └── database.py            # SQLAlchemy models and setup
│
├── tests/                      # Comprehensive test suite
│   ├── test_dkg.py            # DKG security tests
│   ├── test_tss_sign.py       # Threshold signing tests
│   └── test_*.py              # Additional security validation
│
├── asi1/                       # AI processing
│   └── asi1_client.py         # Natural language understanding
│
└── sms-autoreply/             # React Native SMS handler
    ├── services/              # SMS processing services
    ├── hooks/                 # React hooks
    ├── constants/             # App configuration
    └── package.json           # Node.js dependencies
```

## 🚀 Installation & Setup

### Backend Setup

1. **Clone the repository and navigate to project root**:
```bash
git clone <repository-url>
cd sms-tx
```

2. **Create and activate Python virtual environment**:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**:
```bash
python -c "from models.database import init_database; init_database()"
```

6. **Start the backend server**:
```bash
python server.py --participant-id 0
```

### SMS App Setup

1. **Navigate to SMS app directory**:
```bash
cd sms-autoreply
```

2. **Install Node.js dependencies**:
```bash
npm install
```

3. **Start development server**:
```bash
npm run start
```

4. **Build for Android** (requires physical device for SMS functionality):
```bash
npm run android
```

**Note**: SMS functionality requires a physical Android device. iOS has limitations on SMS APIs.

## 📱 Usage Examples

### Getting Your Address
```
SMS to SEC: "What's my address?"
Response: "Your Ethereum address is: 0x742d35..."
```

### Sending Money
```
SMS to SEC: "Send 10 PyUSD to 9876543210"
Response: "✅ Sent 10 PyUSD to 9876543210. Transaction: https://sepolia.arbiscan.io/tx/0x..."
```

### Checking Balance
```
SMS to SEC: "What's my balance?"
Response: "Your balance: 25.50 PyUSD"
```

### Auto-Onboarding Recipients
```
SMS to SEC: "Send 5 PyUSD to 8765432109"
Response: "✅ Sent 5 PyUSD to 8765432109 (new user auto-onboarded). Transaction: https://..."
```

## 🔒 Security Model

### Threat Model
- **Assumed Secure**: Honest majority of threshold nodes, secure communication channels
- **Protected Against**:
  - Individual node compromise
  - Malicious participants in DKG/TSS
  - Network-level attacks
  - SMS interception (transactions require blockchain confirmation)

### Security Assumptions
1. **Threshold Honest**: At least `t` out of `n` nodes remain honest
2. **Secure Channels**: Node-to-node communication is authenticated and encrypted
3. **Phone Number Control**: Users control their registered phone numbers
4. **Blockchain Security**: Underlying Ethereum network security assumptions

### Cryptographic Guarantees
- ✅ **Unforgeability**: Cannot create valid signatures without threshold participation
- ✅ **Robustness**: System continues operating with up to `n-t` node failures
- ✅ **Privacy**: Individual key shares reveal no information about the group key
- ✅ **Non-Repudiation**: All transactions are cryptographically verifiable

## 🧪 Development & Testing

### Running Tests
```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_dkg.py          # DKG security tests
pytest tests/test_tss_sign.py     # Threshold signing tests
pytest tests/test_database.py     # Database integration tests
```

### Phone Validation Testing
```bash
# Test phone number validation
python -c "
from utils.phone_validator import validate_transaction_phones
result = validate_transaction_phones('+919876543210', '8765432109')
print(f'Valid: {result.is_valid}, From: {result.formatted_from}, To: {result.formatted_to}')
"
```

### Development Workflow
1. **Backend Changes**: Modify Python files, restart `server.py`
2. **Crypto Changes**: Run relevant tests to ensure security properties hold
3. **SMS App Changes**: Use `npm run start` for hot reload development
4. **Database Changes**: Update models and run migration scripts

## 🤝 Contributing

1. **Security-First**: All cryptographic changes require thorough testing
2. **Test Coverage**: Maintain comprehensive test coverage, especially for security-critical code
3. **Code Review**: All changes require review, particularly cryptographic implementations
4. **Documentation**: Update relevant documentation for any feature changes

### Security Review Process
- **Cryptographic Changes**: Require expert security review
- **Key Management**: Extra scrutiny for any key-related operations
- **Protocol Changes**: Formal verification where possible
- **Penetration Testing**: Regular security assessments

## 📜 License

[Add your license here]

## 🚨 Security Disclaimer

This is experimental software implementing advanced cryptographic protocols. While designed with production-grade security in mind, it should be thoroughly audited before handling significant value. The security assumptions and threat model should be carefully reviewed for your specific use case.

---

**Built with ❤️ and advanced cryptography for the future of accessible, secure finance.**