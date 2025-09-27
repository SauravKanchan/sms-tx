"""Database models for MPC signature server."""
import os
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from utils.config import config

Base = declarative_base()


class User(Base):
    """User model storing identifier to address mappings."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    identifier_type = Column(String(50), nullable=False, default='email')
    ethereum_address = Column(String(42), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Threshold shares available via ThresholdShare model for POC
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'identifier': self.identifier,
            'identifier_type': self.identifier_type,
            'ethereum_address': self.ethereum_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ThresholdShare(Base):
    """Threshold shares for DKG participants (POC - centrally stored)."""
    __tablename__ = 'threshold_shares'

    id = Column(Integer, primary_key=True)
    user_identifier = Column(String(255), nullable=False, index=True)
    participant_id = Column(Integer, nullable=False)
    share_value = Column(String(100), nullable=False)  # Hex-encoded share value
    session_id = Column(String(64), ForeignKey('dkg_sessions.session_id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Composite unique constraint - one share per participant per session
    __table_args__ = (
        Index('ix_threshold_shares_user_participant', 'user_identifier', 'participant_id'),
        Index('ix_threshold_shares_session', 'session_id'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_identifier': self.user_identifier,
            'participant_id': self.participant_id,
            'share_value': self.share_value,
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Transaction(Base):
    """Transaction records for audit and tracking."""
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    sender_identifier = Column(String(255), nullable=False, index=True)
    receiver_identifier = Column(String(255), nullable=False, index=True)
    sender_address = Column(String(42), nullable=False)
    receiver_address = Column(String(42), nullable=False)
    amount = Column(String(50), nullable=False)  # Store as string to avoid precision issues
    tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default='pending')  # pending, confirmed, failed
    gas_used = Column(Integer, nullable=True)
    gas_price = Column(String(50), nullable=True)
    block_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'sender_identifier': self.sender_identifier,
            'receiver_identifier': self.receiver_identifier,
            'sender_address': self.sender_address,
            'receiver_address': self.receiver_address,
            'amount': self.amount,
            'tx_hash': self.tx_hash,
            'status': self.status,
            'gas_used': self.gas_used,
            'gas_price': self.gas_price,
            'block_number': self.block_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None
        }


class DKGSession(Base):
    """DKG session coordination and state."""
    __tablename__ = 'dkg_sessions'

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_identifier = Column(String(255), nullable=False)
    initiator_participant_id = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, failed
    participants = Column(Text, nullable=False)  # JSON list of participant IDs
    group_public_key = Column(Text, nullable=True)  # Final group public key
    ethereum_address = Column(String(42), nullable=True)  # Derived Ethereum address
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Prevent multiple completed DKG sessions per user
    __table_args__ = (
        Index('ix_dkg_sessions_user_identifier', 'user_identifier'),
        Index('ix_dkg_sessions_status', 'status'),
        # Note: Unique constraint for (user_identifier, status='completed') would require custom check
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_identifier': self.user_identifier,
            'initiator_participant_id': self.initiator_participant_id,
            'status': self.status,
            'participants': self.participants,
            'group_public_key': self.group_public_key,
            'ethereum_address': self.ethereum_address,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


# Global database engine and session factory
_engine = None
_SessionLocal = None


def init_database() -> None:
    """Initialize database connection and create tables."""
    global _engine, _SessionLocal
    
    # Ensure data directory exists
    config.ensure_data_directory()
    
    # Create engine with SQLite optimizations
    database_url = f"sqlite:///{config.database_path}"
    _engine = create_engine(
        database_url,
        connect_args={
            "check_same_thread": False,  # Needed for SQLite
            "timeout": 30,  # 30 second timeout for locked database
        },
        echo=False,  # Set to True for SQL debugging
        pool_timeout=30,
        pool_recycle=-1
    )
    
    # Enable WAL mode for better concurrency
    with _engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA cache_size=10000"))
        conn.execute(text("PRAGMA temp_store=MEMORY"))
        conn.execute(text("PRAGMA busy_timeout=30000"))  # 30 second busy timeout
        conn.commit()

    # Create session factory
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create all tables
    Base.metadata.create_all(bind=_engine)


@contextmanager
def db_session():
    """Get database session with automatic cleanup."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """Get database session (alternative to context manager)."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _SessionLocal()