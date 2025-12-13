#!/usr/bin/env python3
"""
WordPress Stack Discovery Service
Automatically discovers WordPress stacks in Docker Swarm and creates:
- Uptime Kuma monitors
- Grafana dashboards
"""

import os
import re
import time
import json
import logging
import requests
import socketio
import docker
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
UPTIME_KUMA_URL = os.getenv('UPTIME_KUMA_URL', 'http://uptime-kuma:3001')
UPTIME_KUMA_USERNAME = os.getenv('UPTIME_KUMA_USERNAME', 'admin')
UPTIME_KUMA_PASSWORD = os.getenv('UPTIME_KUMA_PASSWORD', '')
GRAFANA_URL = os.getenv('GRAFANA_URL', 'http://grafana:3000')
GRAFANA_ADMIN_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
GRAFANA_ADMIN_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes default
STACK_PATTERN = os.getenv('STACK_PATTERN', 'jpolski_.*_prod_.*')
TEMPLATES_DIR = Path('/app/templates')

# Docker socket
DOCKER_SOCKET = '/var/run/docker.sock'


class UptimeKumaClient:
    """Client for Uptime Kuma API using Socket.IO"""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.sio = socketio.Client()
        self.username = username
        self.password = password
        self.connected = False
        self.logged_in = False
        self.monitors_cache = []
        self.login_event = None
    
    def wait_for_service(self, max_retries: int = 30, retry_interval: int = 5):
        """Wait for Uptime Kuma service to be ready"""
        logger.info(f"Waiting for Uptime Kuma at {self.base_url}...")
        
        session = requests.Session()
        for i in range(max_retries):
            try:
                response = session.get(f"{self.base_url}/", timeout=5)
                if response.status_code == 200:
                    logger.info("✅ Uptime Kuma is ready")
                    return True
            except requests.exceptions.RequestException:
                pass
            
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
                    logger.error(f"Response: {self.login_event}")
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
        
        name = monitor_config.get('name')
        if self.monitor_exists(name):
            logger.debug(f"Monitor '{name}' already exists, skipping")
            return False
        
        try:
            payload = {
                'name': name,
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
                logger.info(f"✅ Created monitor: {name}")
                return True
            else:
                error_msg = add_result.get('msg', 'Unknown error') if add_result else 'No response'
                logger.error(f"Failed to create monitor '{name}': {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Error creating monitor '{name}': {e}")
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


class GrafanaClient:
    """Client for Grafana API operations"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = (GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD)
        self.session.headers.update({'Content-Type': 'application/json'})
        self.api_url = f"{GRAFANA_URL}/api"
        self.dashboards_api = f"{self.api_url}/dashboards/db"
        self.search_api = f"{self.api_url}/search"
    
    def dashboard_exists(self, dashboard_title: str) -> bool:
        """Check if dashboard with given title exists"""
        try:
            response = self.session.get(
                self.search_api,
                params={'query': dashboard_title, 'type': 'dash-db'}
            )
            response.raise_for_status()
            dashboards = response.json()
            return any(d['title'] == dashboard_title for d in dashboards)
        except Exception as e:
            logger.error(f"Error checking dashboard existence: {e}")
            return False
    
    def create_dashboard(self, dashboard_data: Dict) -> bool:
        """Create dashboard in Grafana"""
        try:
            payload = {
                'dashboard': dashboard_data,
                'overwrite': False,
                'folderId': None
            }
            response = self.session.post(self.dashboards_api, json=payload)
            response.raise_for_status()
            logger.info(f"Created dashboard: {dashboard_data.get('title')}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 412:
                logger.debug(f"Dashboard already exists: {dashboard_data.get('title')}")
                return False
            logger.error(f"Error creating dashboard: {e}")
            return False


class DockerSwarmClient:
    """Client for Docker Swarm API"""
    
    def __init__(self):
        try:
            self.client = docker.DockerClient(base_url=f'unix://{DOCKER_SOCKET}')
            logger.info("✅ Connected to Docker Swarm")
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise
    
    def get_services(self, pattern: str) -> List[docker.models.services.Service]:
        """Get all services matching the pattern"""
        try:
            all_services = self.client.services.list()
            regex = re.compile(pattern)
            matching_services = [
                svc for svc in all_services
                if regex.match(svc.name)
            ]
            logger.info(f"Found {len(matching_services)} services matching pattern '{pattern}'")
            return matching_services
        except Exception as e:
            logger.error(f"Error fetching services: {e}")
            return []
    
    def extract_stack_info(self, service: docker.models.services.Service) -> Optional[Dict]:
        """Extract stack information from service"""
        try:
            service_name = service.name
            # Extract stack name (everything before last underscore)
            parts = service_name.rsplit('_', 1)
            if len(parts) < 2:
                return None
            
            stack_name = parts[0]
            service_type = parts[1].lower()
            
            # Get service attributes
            attrs = service.attrs
            labels = attrs.get('Spec', {}).get('Labels', {})
            
            # Extract domain from Traefik labels
            domain = None
            for key, value in labels.items():
                if key.startswith('traefik.http.routers.') and key.endswith('.rule'):
                    # Extract domain from Host(...) rule
                    match = re.search(r"Host\(`([^`]+)`\)", value)
                    if match:
                        domain = match.group(1)
                        break
            
            # Get ports
            ports = []
            port_configs = attrs.get('Endpoint', {}).get('Ports', [])
            for port_config in port_configs:
                ports.append({
                    'published': port_config.get('PublishedPort'),
                    'target': port_config.get('TargetPort'),
                    'protocol': port_config.get('Protocol', 'tcp')
                })
            
            return {
                'stack_name': stack_name,
                'service_name': service_name,
                'service_type': service_type,
                'domain': domain,
                'ports': ports,
                'labels': labels
            }
        except Exception as e:
            logger.error(f"Error extracting stack info from {service.name}: {e}")
            return None


class DashboardTemplate:
    """Template manager for dashboard creation"""
    
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
    
    def load_template(self, template_name: str) -> Optional[Dict]:
        """Load template JSON file"""
        template_path = self.templates_dir / f"{template_name}.json"
        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}")
            return None
        
        try:
            with open(template_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {e}")
            return None
    
    def fill_template(self, template: Dict, variables: Dict) -> Dict:
        """Fill template with variables"""
        template_str = json.dumps(template)
        
        # Replace variables
        for key, value in variables.items():
            template_str = template_str.replace(f"{{{{ {key} }}}}", str(value))
            template_str = template_str.replace(f"{{{{ {key.lower()} }}}}", str(value))
        
        return json.loads(template_str)
    
    def get_template_for_service_type(self, service_type: str) -> str:
        """Get template name based on service type"""
        template_map = {
            'wordpress': 'wordpress',
            'mariadb': 'database',
            'mysql': 'database',
            'redis': 'database',
            'wp-cron': 'generic-app',
        }
        return template_map.get(service_type.lower(), 'generic-app')


class WordPressStackDiscovery:
    """Main discovery service"""
    
    def __init__(self):
        self.docker_client = DockerSwarmClient()
        self.uptime_kuma = UptimeKumaClient(UPTIME_KUMA_URL, UPTIME_KUMA_USERNAME, UPTIME_KUMA_PASSWORD)
        self.grafana = GrafanaClient()
        self.template_manager = DashboardTemplate(TEMPLATES_DIR)
        self.processed_stacks: Set[str] = set()
    
    def group_services_by_stack(self, services: List[docker.models.services.Service]) -> Dict[str, List[Dict]]:
        """Group services by stack name"""
        stacks = defaultdict(list)
        
        for service in services:
            info = self.docker_client.extract_stack_info(service)
            if info:
                stacks[info['stack_name']].append(info)
        
        return dict(stacks)
    
    def create_uptime_kuma_monitors(self, stack_name: str, services: List[Dict]):
        """Create Uptime Kuma monitors for a stack"""
        wordpress_service = next((s for s in services if s['service_type'] == 'wordpress'), None)
        mariadb_service = next((s for s in services if s['service_type'] == 'mariadb'), None)
        redis_service = next((s for s in services if s['service_type'] == 'redis'), None)
        
        # WordPress monitor (HTTP)
        if wordpress_service and wordpress_service.get('domain'):
            domain = wordpress_service['domain']
            monitor_config = {
                'name': f"{stack_name} - WordPress",
                'type': 'http',
                'url': f"https://{domain}",
                'interval': 60,
                'retries': 2,
                'timeout': 10
            }
            self.uptime_kuma.create_monitor(monitor_config)
        
        # MariaDB monitor (TCP)
        if mariadb_service:
            monitor_config = {
                'name': f"{stack_name} - MariaDB",
                'type': 'tcp',
                'url': mariadb_service['service_name'],
                'port': 3306,
                'interval': 60,
                'retries': 2,
                'timeout': 10
            }
            self.uptime_kuma.create_monitor(monitor_config)
        
        # Redis monitor (TCP)
        if redis_service:
            monitor_config = {
                'name': f"{stack_name} - Redis",
                'type': 'tcp',
                'url': redis_service['service_name'],
                'port': 6379,
                'interval': 60,
                'retries': 2,
                'timeout': 10
            }
            self.uptime_kuma.create_monitor(monitor_config)
    
    def create_grafana_dashboards(self, stack_name: str, services: List[Dict]):
        """Create Grafana dashboards for a stack"""
        for service_info in services:
            service_type = service_info['service_type']
            service_name = service_info['service_name']
            
            # Skip wp-cron (no need for separate dashboard)
            if service_type == 'wp-cron':
                continue
            
            # Get template
            template_name = self.template_manager.get_template_for_service_type(service_type)
            template = self.template_manager.load_template(template_name)
            
            if not template:
                logger.warning(f"No template found for {service_type}, skipping dashboard")
                continue
            
            # Create dashboard title
            dashboard_title = f"{stack_name} - {service_type.title()}"
            
            # Check if dashboard already exists
            if self.grafana.dashboard_exists(dashboard_title):
                logger.debug(f"Dashboard already exists: {dashboard_title}")
                continue
            
            # Fill template
            dashboard = self.template_manager.fill_template(template, {
                'app_name': stack_name,
                'service_name': service_name,
                'app_type': service_type,
                'container_name': service_name,
                'job': service_name,
                'instance': service_name,
            })
            
            # Update dashboard metadata
            dashboard['title'] = dashboard_title
            dashboard['uid'] = f"{stack_name}-{service_type}".lower().replace('_', '-')
            dashboard['tags'] = [service_type, stack_name, 'auto-generated', 'wordpress-stack']
            
            # Create dashboard
            self.grafana.create_dashboard(dashboard)
    
    def process_stack(self, stack_name: str, services: List[Dict]):
        """Process a single stack"""
        logger.info(f"Processing stack: {stack_name} ({len(services)} services)")
        
        # Create Uptime Kuma monitors
        self.create_uptime_kuma_monitors(stack_name, services)
        
        # Create Grafana dashboards
        self.create_grafana_dashboards(stack_name, services)
        
        self.processed_stacks.add(stack_name)
    
    def run_discovery(self):
        """Run one discovery cycle"""
        logger.info("Starting WordPress stack discovery...")
        
        # Get services matching pattern
        services = self.docker_client.get_services(STACK_PATTERN)
        
        if not services:
            logger.info("No WordPress stacks found")
            return
        
        # Group services by stack
        stacks = self.group_services_by_stack(services)
        
        logger.info(f"Found {len(stacks)} WordPress stacks")
        
        # Process each stack
        for stack_name, stack_services in stacks.items():
            try:
                self.process_stack(stack_name, stack_services)
            except Exception as e:
                logger.error(f"Error processing stack {stack_name}: {e}")
    
    def run(self):
        """Main loop"""
        logger.info("Starting WordPress Stack Discovery Service")
        logger.info(f"Stack pattern: {STACK_PATTERN}")
        logger.info(f"Check interval: {CHECK_INTERVAL}s")
        logger.info(f"Uptime Kuma URL: {UPTIME_KUMA_URL}")
        logger.info(f"Uptime Kuma Username: {UPTIME_KUMA_USERNAME}")
        logger.info(f"Uptime Kuma Password: {'***' if UPTIME_KUMA_PASSWORD else 'NOT SET'}")
        logger.info(f"Grafana URL: {GRAFANA_URL}")
        
        # Wait for Uptime Kuma
        if not self.uptime_kuma.wait_for_service():
            logger.error("Uptime Kuma not available, exiting")
            return
        
        # Login to Uptime Kuma
        if not self.uptime_kuma.login():
            logger.error("Failed to login to Uptime Kuma, exiting")
            logger.error("Please check:")
            logger.error("1. UPTIME_KUMA_USERNAME is set in Portainer environment variables")
            logger.error("2. UPTIME_KUMA_PASSWORD is set in Portainer environment variables")
            logger.error("3. Credentials match the Uptime Kuma admin account")
            return
        
        # Run discovery loop
        while True:
            try:
                self.run_discovery()
            except Exception as e:
                logger.error(f"Error in discovery cycle: {e}")
            
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    discovery = WordPressStackDiscovery()
    discovery.run()

