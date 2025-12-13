#!/usr/bin/env python3
"""
Uptime Kuma Initialization Script
Loads configuration from YAML file and initializes monitors via Uptime Kuma API
"""

import os
import time
import yaml
import requests
import socketio
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
    """Client for Uptime Kuma API using Socket.IO"""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        # Extract hostname and port from URL
        if self.base_url.startswith('http://'):
            socket_url = self.base_url.replace('http://', 'ws://')
        elif self.base_url.startswith('https://'):
            socket_url = self.base_url.replace('https://', 'wss://')
        else:
            socket_url = f"ws://{self.base_url}"
        
        self.sio = socketio.Client()
        self.username = username
        self.password = password
        self.connected = False
        self.logged_in = False
        self.monitors_cache = []
        self.login_event = None
    
    def wait_for_service(self, max_retries: int = MAX_RETRIES, retry_interval: int = RETRY_INTERVAL):
        """Wait for Uptime Kuma service to be ready"""
        logger.info(f"Waiting for Uptime Kuma at {self.base_url}...")
        
        session = requests.Session()
        for i in range(max_retries):
            try:
                response = session.get(f"{self.base_url}/", timeout=5)
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
        """Login to Uptime Kuma using Socket.IO"""
        if not self.username:
            logger.error("UPTIME_KUMA_USERNAME is not set")
            return False
        
        if not self.password:
            logger.error("UPTIME_KUMA_PASSWORD is not set - please set it in Portainer environment variables")
            return False
        
        try:
            # Connect to Socket.IO server
            socket_url = self.base_url.replace('http://', 'ws://').replace('https://', 'wss://')
            logger.info(f"Connecting to Uptime Kuma Socket.IO at {socket_url}...")
            
            self.login_event = None
            
            @self.sio.event
            def connect():
                logger.info("✅ Connected to Uptime Kuma Socket.IO")
                self.connected = True
            
            @self.sio.event
            def disconnect():
                logger.warning("Disconnected from Uptime Kuma Socket.IO")
                self.connected = False
            
            @self.sio.on('login')
            def on_login(data):
                self.login_event = data
            
            self.sio.connect(socket_url, wait_timeout=10)
            
            # Wait for connection
            time.sleep(1)
            
            if not self.connected:
                logger.error("Failed to connect to Uptime Kuma Socket.IO")
                return False
            
            # Send login event
            logger.info(f"Attempting to login as user: {self.username}")
            self.sio.emit('login', {
                'username': self.username,
                'password': self.password
            })
            
            # Wait for login response
            time.sleep(2)
            
            if self.login_event:
                if self.login_event.get('ok'):
                    self.logged_in = True
                    logger.info("✅ Logged in to Uptime Kuma")
                    return True
                else:
                    error_msg = self.login_event.get('msg', 'Unknown error')
                    logger.error(f"Login failed: {error_msg}")
                    return False
            else:
                logger.error("No response from login event")
                return False
                
        except Exception as e:
            logger.error(f"Error during login: {e}", exc_info=True)
            return False
    
    def get_monitors(self) -> List[Dict]:
        """Get all existing monitors"""
        if not self.logged_in:
            logger.error("Not logged in to Uptime Kuma")
            return []
        
        try:
            monitors_event = None
            
            @self.sio.on('monitors')
            def on_monitors(data):
                nonlocal monitors_event
                monitors_event = data
            
            self.sio.emit('getMonitorsList')
            time.sleep(1)
            
            if monitors_event:
                return monitors_event.get('monitors', [])
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
        if not self.logged_in:
            logger.error("Not logged in to Uptime Kuma")
            return False
        
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
            
            # Add TCP-specific fields if needed
            if monitor_config.get('type') == 'tcp':
                payload['port'] = monitor_config.get('port', 3306)
            
            add_result = None
            
            @self.sio.on('addMonitor')
            def on_add_monitor(data):
                nonlocal add_result
                add_result = data
            
            self.sio.emit('addMonitor', payload)
            time.sleep(1)
            
            if add_result and add_result.get('ok'):
                logger.info(f"✅ Created monitor: {monitor_config['name']}")
                return True
            else:
                error_msg = add_result.get('msg', 'Unknown error') if add_result else 'No response'
                logger.error(f"Failed to create monitor '{monitor_config['name']}': {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Error creating monitor '{monitor_config.get('name')}': {e}")
            return False
    
    def update_monitor(self, monitor_id: int, monitor_config: Dict) -> bool:
        """Update an existing monitor"""
        if not self.logged_in:
            logger.error("Not logged in to Uptime Kuma")
            return False
        
        try:
            payload = {
                'id': monitor_id,
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
            
            update_result = None
            
            @self.sio.on('editMonitor')
            def on_edit_monitor(data):
                nonlocal update_result
                update_result = data
            
            self.sio.emit('editMonitor', payload)
            time.sleep(1)
            
            if update_result and update_result.get('ok'):
                logger.info(f"✅ Updated monitor: {monitor_config.get('name')}")
                return True
            else:
                error_msg = update_result.get('msg', 'Unknown error') if update_result else 'No response'
                logger.error(f"Failed to update monitor '{monitor_config.get('name')}': {error_msg}")
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

