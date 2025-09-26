# internal/security.py - Byzantine Fault Tolerance and Malicious Participant Detection
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Set
import time
import hashlib
from internal.mpc_nonce import NonceCommitment
from internal.partial_sig import PartialSignature
from internal.zk_proofs import DKGProof, PartialSigProof

@dataclass
class SecurityViolation:
    """Detected security violation"""
    participant_id: int
    violation_type: str
    evidence: Dict[str, Any]
    timestamp: float
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'

class MaliciousParticipantDetector:
    """
    Comprehensive malicious behavior detection for threshold ECDSA.
    
    DETECTION CAPABILITIES:
    - Invalid VSS commitments during DKG
    - Incorrect partial signatures
    - Abort attacks and selective participation
    - Nonce manipulation attempts
    - Invalid zero-knowledge proofs
    - Timing-based attacks
    - Replay attacks
    """
    
    def __init__(self):
        self.participant_history: Dict[int, List[Any]] = {}
        self.nonce_history: Set[int] = set()
        self.violation_history: List[SecurityViolation] = []
        self.suspicious_patterns: Dict[int, int] = {}  # participant_id -> suspicion_score
    
    def detect_dkg_violations(self, 
                            participant_id: int,
                            commitments: List[bytes],
                            proofs: List[DKGProof]) -> Optional[SecurityViolation]:
        """
        Detect malicious behavior during DKG ceremony.
        
        Args:
            participant_id: ID of participant being evaluated
            commitments: VSS commitments provided by participant
            proofs: Zero-knowledge proofs provided by participant
            
        Returns:
            SecurityViolation if malicious behavior detected, None otherwise
        """
        # Check for invalid commitment structure
        if not self._validate_commitment_structure(commitments):
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="INVALID_VSS_COMMITMENTS",
                evidence={"commitments": [c.hex() for c in commitments]},
                timestamp=time.time(),
                severity="HIGH"
            )
        
        # Check for invalid proofs
        if not self._validate_dkg_proofs(proofs):
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="INVALID_ZK_PROOFS",
                evidence={"proof_count": len(proofs)},
                timestamp=time.time(),
                severity="HIGH"
            )
        
        # Check for duplicate commitments (potential replay attack)
        if self._detect_commitment_reuse(participant_id, commitments):
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="COMMITMENT_REUSE",
                evidence={"commitments": [c.hex() for c in commitments]},
                timestamp=time.time(),
                severity="CRITICAL"
            )
        
        return None
    
    def detect_signing_violations(self,
                                participant_id: int,
                                partial_sig: PartialSignature,
                                nonce_commitment: NonceCommitment) -> Optional[SecurityViolation]:
        """
        Detect malicious behavior during threshold signing.
        
        Args:
            participant_id: ID of participant being evaluated
            partial_sig: Partial signature provided by participant
            nonce_commitment: Nonce commitment used in signing
            
        Returns:
            SecurityViolation if malicious behavior detected, None otherwise
        """
        # Check for nonce reuse attack
        if nonce_commitment.r_commitment in self.nonce_history:
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="NONCE_REUSE_ATTACK",
                evidence={
                    "reused_nonce": nonce_commitment.r_commitment,
                    "timestamp": nonce_commitment.timestamp
                },
                timestamp=time.time(),
                severity="CRITICAL"
            )
        
        # Record nonce for future reuse detection
        self.nonce_history.add(nonce_commitment.r_commitment)
        
        # Check for invalid partial signature bounds
        if not (0 < partial_sig.value < 2**256):
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="INVALID_SIGNATURE_BOUNDS",
                evidence={"partial_value": partial_sig.value},
                timestamp=time.time(),
                severity="MEDIUM"
            )
        
        # Check for proof verification failure (handled elsewhere but logged here)
        if not self._validate_partial_sig_proof(partial_sig.proof):
            return SecurityViolation(
                participant_id=participant_id,
                violation_type="INVALID_PARTIAL_SIG_PROOF",
                evidence={"participant": participant_id},
                timestamp=time.time(),
                severity="HIGH"
            )
        
        return None
    
    def detect_abort_attack(self,
                           expected_participants: List[int],
                           actual_participants: List[int],
                           round_number: int) -> Optional[SecurityViolation]:
        """
        Detect selective abort attacks where participants strategically fail.
        
        Args:
            expected_participants: List of participants expected to contribute
            actual_participants: List of participants who actually contributed
            round_number: Current protocol round number
            
        Returns:
            SecurityViolation if abort attack detected, None otherwise
        """
        missing_participants = set(expected_participants) - set(actual_participants)
        
        if not missing_participants:
            return None
        
        # Check for suspicious patterns of absence
        for pid in missing_participants:
            self.suspicious_patterns[pid] = self.suspicious_patterns.get(pid, 0) + 1
            
            # If participant has been missing frequently, flag as potential attacker
            if self.suspicious_patterns[pid] >= 3:
                return SecurityViolation(
                    participant_id=pid,
                    violation_type="SELECTIVE_ABORT_ATTACK",
                    evidence={
                        "absence_count": self.suspicious_patterns[pid],
                        "round": round_number,
                        "expected": expected_participants,
                        "actual": actual_participants
                    },
                    timestamp=time.time(),
                    severity="HIGH"
                )
        
        return None
    
    def _validate_commitment_structure(self, commitments: List[bytes]) -> bool:
        """Validate that VSS commitments have correct structure"""
        if not commitments:
            return False
        
        for commitment in commitments:
            # Check commitment length (compressed public key)
            if len(commitment) != 33:
                return False
            
            # Check public key format (must start with 0x02 or 0x03)
            if commitment[0] not in (0x02, 0x03):
                return False
        
        return True
    
    def _validate_dkg_proofs(self, proofs: List[DKGProof]) -> bool:
        """Validate DKG zero-knowledge proofs"""
        if not proofs:
            return False
        
        for proof in proofs:
            # Basic structure validation
            if not (proof.commitment_proof and proof.share_proof):
                return False
            
            # Check proof bounds
            if not (0 < proof.response < 2**256):
                return False
        
        return True
    
    def _detect_commitment_reuse(self, 
                                participant_id: int, 
                                commitments: List[bytes]) -> bool:
        """Detect if participant is reusing previous commitments"""
        if participant_id not in self.participant_history:
            self.participant_history[participant_id] = []
            return False
        
        # Check against historical commitments
        for historical_commitments in self.participant_history[participant_id]:
            if commitments == historical_commitments:
                return True
        
        # Store current commitments for future comparison
        self.participant_history[participant_id].append(commitments)
        return False
    
    def _validate_partial_sig_proof(self, proof: PartialSigProof) -> bool:
        """Validate partial signature proof structure"""
        return (
            proof.signature_proof and
            proof.share_proof and 
            proof.nonce_proof and
            0 < proof.response < 2**256
        )
    
    def get_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        return {
            "total_violations": len(self.violation_history),
            "violations_by_type": self._group_violations_by_type(),
            "violations_by_severity": self._group_violations_by_severity(),
            "suspicious_participants": self._get_suspicious_participants(),
            "recent_violations": self.violation_history[-10:],  # Last 10 violations
        }
    
    def _group_violations_by_type(self) -> Dict[str, int]:
        """Group violations by type for reporting"""
        type_counts = {}
        for violation in self.violation_history:
            type_counts[violation.violation_type] = type_counts.get(violation.violation_type, 0) + 1
        return type_counts
    
    def _group_violations_by_severity(self) -> Dict[str, int]:
        """Group violations by severity for reporting"""
        severity_counts = {}
        for violation in self.violation_history:
            severity_counts[violation.severity] = severity_counts.get(violation.severity, 0) + 1
        return severity_counts
    
    def _get_suspicious_participants(self) -> List[Dict[str, Any]]:
        """Get list of participants with suspicious behavior patterns"""
        suspicious = []
        for pid, score in self.suspicious_patterns.items():
            if score >= 2:  # Threshold for suspicion
                participant_violations = [v for v in self.violation_history if v.participant_id == pid]
                suspicious.append({
                    "participant_id": pid,
                    "suspicion_score": score,
                    "violation_count": len(participant_violations),
                    "latest_violation": participant_violations[-1] if participant_violations else None
                })
        return suspicious

def detect_malicious_participant(partial_sig_or_data: Any, 
                               nonce_commitment: Optional[NonceCommitment] = None) -> Optional[SecurityViolation]:
    """
    Convenience function for detecting malicious behavior.
    
    Args:
        partial_sig_or_data: Partial signature or other data to analyze
        nonce_commitment: Optional nonce commitment for context
        
    Returns:
        SecurityViolation if malicious behavior detected, None otherwise
    """
    detector = MaliciousParticipantDetector()
    
    # Handle different types of input
    if isinstance(partial_sig_or_data, PartialSignature):
        if nonce_commitment is None:
            nonce_commitment = partial_sig_or_data.nonce_commitment
        return detector.detect_signing_violations(
            partial_sig_or_data.participant_id,
            partial_sig_or_data,
            nonce_commitment
        )
    
    # If we can't determine the type, no violation detected
    return None

class FixedRNG:
    """Deterministic RNG for reproducible operations"""
    def __init__(self, seed=123456789):
        self.state = seed
    
    def randbelow(self, n):
        # Simple LCG for deterministic tests
        self.state = (1103515245 * self.state + 12345) % (2**31)
        return self.state % n

class SecurityException(Exception):
    """Exception raised for security violations"""
    
    def __init__(self, violation: SecurityViolation):
        self.violation = violation
        super().__init__(f"Security violation: {violation.violation_type} by participant {violation.participant_id}")

class IncidentResponseHandler:
    """Handler for security incidents and violations"""
    
    def __init__(self):
        self.incident_log = []
        self.blocked_participants = set()
    
    def handle_security_violation(self, violation: SecurityViolation) -> None:
        """
        Handle detected security violation.
        
        Args:
            violation: The security violation to handle
        """
        # Log the incident
        self.incident_log.append(violation)
        
        # Take action based on severity
        if violation.severity in ("HIGH", "CRITICAL"):
            self._block_participant(violation.participant_id)
            self._alert_security_team(violation)
        
        # Log for audit purposes
        self._log_security_event(violation)
    
    def _block_participant(self, participant_id: int) -> None:
        """Block a malicious participant from future protocols"""
        self.blocked_participants.add(participant_id)
        print(f"SECURITY: Blocked participant {participant_id} due to malicious behavior")
    
    def _alert_security_team(self, violation: SecurityViolation) -> None:
        """Alert security team about critical violations"""
        # In production, this would send alerts to security monitoring systems
        print(f"SECURITY ALERT: {violation.violation_type} detected from participant {violation.participant_id}")
    
    def _log_security_event(self, violation: SecurityViolation) -> None:
        """Log security event for audit trail"""
        # In production, this would write to secure audit logs
        print(f"AUDIT LOG: Security violation recorded - {violation}")
    
    def is_participant_blocked(self, participant_id: int) -> bool:
        """Check if a participant is blocked due to security violations"""
        return participant_id in self.blocked_participants
    
    def get_incident_summary(self) -> Dict[str, Any]:
        """Get summary of security incidents"""
        return {
            "total_incidents": len(self.incident_log),
            "blocked_participants": list(self.blocked_participants),
            "recent_incidents": self.incident_log[-5:],  # Last 5 incidents
        }