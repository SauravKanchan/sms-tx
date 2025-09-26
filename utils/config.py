"""Configuration management for MPC signature server."""
import json
import os
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv


class Config:
    """Configuration manager for MPC signature server."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize configuration from JSON file and environment variables."""
        # Load environment variables from .env file
        load_dotenv()
        
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in configuration file: {e}")
    
    def get_server_config(self, participant_id: int) -> Dict[str, Any]:
        """Get configuration for specific server participant."""
        servers = self._config.get("servers", [])
        for server in servers:
            if server["id"] == participant_id:
                return server
        raise ValueError(f"Server configuration not found for participant {participant_id}")
    
    def get_other_servers(self, participant_id: int) -> List[Dict[str, Any]]:
        """Get configuration for other server participants."""
        servers = self._config.get("servers", [])
        return [s for s in servers if s["id"] != participant_id]
    
    @property
    def database_path(self) -> str:
        """Get database file path."""
        return self._config["database"]["path"]
    
    @property
    def blockchain_config(self) -> Dict[str, Any]:
        """Get blockchain configuration."""
        return self._config["blockchain"]
    
    @property
    def threshold_config(self) -> Dict[str, int]:
        """Get threshold configuration."""
        return self._config["threshold"]
    
    @property
    def mpc_config(self) -> Dict[str, Any]:
        """Get MPC configuration."""
        return self._config.get("mpc", {})
    
    @property
    def rpc_url(self) -> str:
        """Get blockchain RPC URL."""
        return self.blockchain_config["rpc_url"]
    
    @property
    def chain_id(self) -> int:
        """Get blockchain chain ID."""
        return self.blockchain_config["chain_id"]
    
    @property
    def usdc_contract(self) -> str:
        """Get USDC contract address."""
        return self.blockchain_config["usdc_contract"]
    
    @property
    def faucet_private_key(self) -> str:
        """Get faucet private key from environment variable or config file."""
        # Try environment variable first
        env_key = os.getenv("FAUCET_PRIVATE_KEY")
        if env_key:
            # Validate that it's not the default placeholder key
            if env_key == "0x0000000000000000000000000000000000000000000000000000000000000001":
                raise ValueError(
                    "FAUCET_PRIVATE_KEY is set to placeholder value. "
                    "Please set a real private key in your .env file."
                )
            return env_key
        
        # Fall back to config file
        config_key = self.blockchain_config.get("faucet_private_key")
        if config_key and config_key != "0x0000000000000000000000000000000000000000000000000000000000000001":
            return config_key
            
        raise ValueError(
            "No valid faucet private key found. Please set FAUCET_PRIVATE_KEY environment variable "
            "or update the faucet_private_key in config.json with a real private key."
        )
    
    @property
    def faucet_amount_eth(self) -> str:
        """Get faucet ETH amount."""
        return self.blockchain_config["faucet_amount_eth"]
    
    @property
    def threshold_required(self) -> int:
        """Get required threshold for signing."""
        return self.threshold_config["required"]
    
    @property
    def threshold_total(self) -> int:
        """Get total number of participants."""
        return self.threshold_config["total"]
    
    def ensure_data_directory(self) -> None:
        """Ensure data directory exists."""
        db_dir = os.path.dirname(self.database_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)


# Global configuration instance
config = Config()