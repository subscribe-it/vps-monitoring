#!/usr/bin/env python3
"""
Uptime Kuma Initialization Script
Loads configuration from YAML file and initializes monitors via Uptime Kuma API
"""

import os
import time
import yaml
import requests
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
UPTIME_KUMA_URL = os.getenv('UPTIME_KUMA_URL', 'http://localhost:3001')
UPTIME_KUMA_USERNAME = os.getenv('UPTIME_KUMA_USERNAME', 'admin')
UPTIME_KUMA_PASSWORD = os.getenv('UPTIME_KUMA_PASSWORD', '')
CONFIG_FILE = Path('/app/config/uptime-kuma-config.yaml')
MAX_RETRIES = 30
RETRY_INTERVAL = 5


class UptimeKumaClient:
    """Client for Uptime Kuma API"""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.token = None
    
    def wait_for_service(self, max_retries: int = MAX_RETRIES, retry_interval: int = RETRY_INTERVAL):
        """Wait for Uptime Kuma service to be ready"""
        logger.info(f"Waiting for Uptime Kuma at {self.base_url}...")
        
        for i in range(max_retries):
            try:
                response = self.session.get(f"{self.base_url}/", timeout=5)
                if response.status_code == 200:
                    logger.info("✅ Uptime Kuma is ready")
                    return True
            except requests.exceptions.RequestException as e:
                logger.debug(f"Attempt {i+1}/{max_retries}: {e}")
            
            if i < max_retries - 1:
                time.sleep(retry_interval)
        
        logger.error(f"❌ Uptime Kuma not available after {max_retries} attempts")
        return False
    
    def login(self) -> bool:
        """Login to Uptime Kuma"""
        try:
            response = self.session.post(
                f"{self.api_url}/login",
                json={
                    'username': self.username,
                    'password': self.password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    self.token = data.get('token')
                    logger.info("✅ Logged in to Uptime Kuma")
                    return True
                else:
                    logger.error(f"Login failed: {data.get('msg', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Login failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False
    
    def get_monitors(self) -> List[Dict]:
        """Get all existing monitors"""
        try:
            response = self.session.get(
                f"{self.api_url}/monitors",
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('monitors', [])
            return []
        except Exception as e:
            logger.error(f"Error fetching monitors: {e}")
            return []
    
    def monitor_exists(self, name: str) -> bool:
        """Check if monitor with given name exists"""
        monitors = self.get_monitors()
        return any(m.get('name') == name for m in monitors)
    
    def create_monitor(self, monitor_config: Dict) -> bool:
        """Create a monitor in Uptime Kuma"""
        if self.monitor_exists(monitor_config.get('name')):
            logger.debug(f"Monitor '{monitor_config['name']}' already exists, skipping")
            return False
        
        try:
            payload = {
                'name': monitor_config.get('name'),
                'type': monitor_config.get('type', 'http'),
                'url': monitor_config.get('url'),
                'interval': monitor_config.get('interval', 60),
                'retries': monitor_config.get('retries', 2),
                'timeout': monitor_config.get('timeout', 10),
            }
            
            response = self.session.post(
                f"{self.api_url}/monitors",
                json=payload,
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Created monitor: {monitor_config['name']}")
                return True
            else:
                logger.error(f"Failed to create monitor '{monitor_config['name']}': {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error creating monitor '{monitor_config.get('name')}': {e}")
            return False
    
    def update_monitor(self, monitor_id: int, monitor_config: Dict) -> bool:
        """Update an existing monitor"""
        try:
            payload = {
                'name': monitor_config.get('name'),
                'type': monitor_config.get('type', 'http'),
                'url': monitor_config.get('url'),
                'interval': monitor_config.get('interval', 60),
                'retries': monitor_config.get('retries', 2),
                'timeout': monitor_config.get('timeout', 10),
            }
            
            # Add TCP-specific fields if needed
            if monitor_config.get('type') == 'tcp':
                payload['port'] = monitor_config.get('port', 3306)
            
            response = self.session.put(
                f"{self.api_url}/monitors/{monitor_id}",
                json=payload,
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Updated monitor: {monitor_config.get('name')}")
                return True
            else:
                logger.error(f"Failed to update monitor '{monitor_config.get('name')}': {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error updating monitor '{monitor_config.get('name')}': {e}")
            return False


def load_config(config_file: Path) -> Optional[Dict]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_file}")
        return None
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Substitute environment variables
        config_str = yaml.dump(config)
        for key, value in os.environ.items():
            config_str = config_str.replace(f"${{{key}}}", str(value))
            config_str = config_str.replace(f"${{{key}:-}}", str(value))
        
        config = yaml.safe_load(config_str)
        logger.info(f"✅ Loaded configuration from {config_file}")
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None


def main():
    """Main initialization function"""
    logger.info("Starting Uptime Kuma initialization...")
    
    # Load configuration
    config = load_config(CONFIG_FILE)
    if not config:
        logger.warning("No configuration file found, skipping initialization")
        return
    
    # Initialize client
    client = UptimeKumaClient(
        UPTIME_KUMA_URL,
        UPTIME_KUMA_USERNAME,
        UPTIME_KUMA_PASSWORD
    )
    
    # Wait for service
    if not client.wait_for_service():
        logger.error("Uptime Kuma service not available, exiting")
        return
    
    # Login
    if not client.login():
        logger.error("Failed to login to Uptime Kuma, exiting")
        return
    
    # Create monitors from config
    monitors = config.get('monitors', [])
    if monitors:
        logger.info(f"Creating {len(monitors)} monitors from configuration...")
        for monitor in monitors:
            client.create_monitor(monitor)
    else:
        logger.info("No monitors defined in configuration")
    
    logger.info("✅ Uptime Kuma initialization completed")


if __name__ == '__main__':
    main()

