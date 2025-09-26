# internal/eth.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
from eth_utils import keccak
from coincurve import PublicKey, PrivateKey
from coincurve.ecdsa import der_to_cdata, cdata_to_der
from eth_keys.datatypes import Signature as EthSignature
from eth_keys.main import PublicKey as EthPublicKey

# secp256k1 order
N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def keccak256(msg: bytes) -> bytes:
    return keccak(msg)

def to_low_s(r: int, s: int) -> Tuple[int, int, bool]:
    """Ensure EIP-2 low-S; return (r, s_norm, flipped) where flipped indicates if s was inverted."""
    if s > N // 2:
        return r, N - s, True
    return r, s, False

def ecdsa_sign_raw(privkey_int: int, digest32: bytes) -> Tuple[int, int, int]:
    """Return (r, s, v) with low-S canonicalization and Ethereum recovery id.
    NOTE: This uses single-party ECDSA and is used by the toy combiner."""
    pk = PrivateKey(privkey_int.to_bytes(32, "big"))
    # coincurve returns a 65-byte sig: [r||s||v] where v in {0,1,2,3}
    sig65 = pk.sign_recoverable(digest32, hasher=None)
    r = int.from_bytes(sig65[0:32], "big")
    s = int.from_bytes(sig65[32:64], "big")
    v = sig65[64]
    
    # Convert v from coincurve format (0-3) to Ethereum format (27-28)
    # For standard ECDSA, v should be 27 or 28
    if v >= 2:
        v = v - 2
    v = v + 27
    
    r, s, flipped = to_low_s(r, s)
    if flipped:
        # If we flip S, flip recovery id parity.
        v = 27 if v == 28 else 28
    return r, s, v

def recover_pubkey(digest32: bytes, r: int, s: int, v: int) -> bytes:
    """Recover uncompressed pubkey (65 bytes, 0x04 prefix)."""
    # Convert v from Ethereum format (27-28) to coincurve format (0-3)
    if v >= 27:
        recovery_id = v - 27
    else:
        recovery_id = v
    
    sig65 = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([recovery_id])
    pub = PublicKey.from_signature_and_message(sig65, digest32, hasher=None)
    return pub.format(compressed=False)

def pubkey_to_eth_address(uncompressed_65: bytes) -> str:
    assert uncompressed_65[0] == 0x04
    h = keccak(uncompressed_65[1:])
    return "0x" + h[-20:].hex()

def verify_eth_sig(digest32: bytes, r: int, s: int, v: int, expected_uncompressed_65: bytes) -> bool:
    rec = recover_pubkey(digest32, r, s, v)
    return rec == expected_uncompressed_65

def priv_to_pub_uncompressed(privkey_int: int) -> bytes:
    pk = PrivateKey(privkey_int.to_bytes(32, "big"))
    return pk.public_key.format(compressed=False)

def compute_recovery_id(r: int, s: int, digest: bytes, expected_pubkey: bytes) -> int:
    """Compute Ethereum recovery ID (v) that allows recovery of the correct public key."""
    # Try both recovery IDs (27 and 28) to find the correct one
    for v in [27, 28]:
        try:
            recovered = recover_pubkey(digest, r, s, v)
            if recovered == expected_pubkey:
                return v
        except Exception:
            continue
    
    # If neither works, default to 27 (this shouldn't happen with valid signatures)
    return 27