#!/usr/bin/env python3
"""
Automated Dashboard Creator for Grafana
Monitors Prometheus targets and automatically creates Grafana dashboards
for newly discovered services.
"""

import os
import time
import json
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

# Configuration from environment
GRAFANA_URL = os.getenv('GRAFANA_URL', 'http://grafana:3000')
GRAFANA_ADMIN_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
GRAFANA_ADMIN_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin')
PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))
TEMPLATES_DIR = Path('/app/templates')

# Grafana API endpoints
GRAFANA_API = f"{GRAFANA_URL}/api"
GRAFANA_DASHBOARDS_API = f"{GRAFANA_API}/dashboards/db"
GRAFANA_SEARCH_API = f"{GRAFANA_API}/search"
PROMETHEUS_TARGETS_API = f"{PROMETHEUS_URL}/api/v1/targets"


class GrafanaClient:
    """Client for Grafana API operations"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = (GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD)
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def dashboard_exists(self, dashboard_title: str) -> bool:
        """Check if dashboard with given title exists"""
        try:
            response = self.session.get(
                GRAFANA_SEARCH_API,
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
            response = self.session.post(GRAFANA_DASHBOARDS_API, json=payload)
            response.raise_for_status()
            logger.info(f"Created dashboard: {dashboard_data.get('title')}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 412:
                logger.debug(f"Dashboard already exists: {dashboard_data.get('title')}")
                return False
            logger.error(f"Error creating dashboard: {e}")
            return False


class PrometheusClient:
    """Client for Prometheus API operations"""
    
    def __init__(self):
        self.session = requests.Session()
    
    def get_active_targets(self) -> List[Dict]:
        """Get all active targets from Prometheus"""
        try:
            response = self.session.get(PROMETHEUS_TARGETS_API)
            response.raise_for_status()
            data = response.json()
            
            active_targets = []
            for target in data.get('data', {}).get('activeTargets', []):
                if target.get('health') == 'up':
                    active_targets.append(target)
            
            return active_targets
        except Exception as e:
            logger.error(f"Error fetching Prometheus targets: {e}")
            return []


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
    
    def get_template_for_app_type(self, app_type: str) -> str:
        """Get template name based on app type"""
        template_map = {
            'wordpress': 'wordpress',
            'database': 'database',
            'mariadb': 'database',
            'mysql': 'database',
            'postgres': 'database',
            'redis': 'database',
        }
        return template_map.get(app_type.lower(), 'generic-app')


class DashboardAutomation:
    """Main automation class"""
    
    def __init__(self):
        self.grafana = GrafanaClient()
        self.prometheus = PrometheusClient()
        self.template_manager = DashboardTemplate(TEMPLATES_DIR)
        self.processed_targets = set()
    
    def extract_labels(self, target: Dict) -> Dict:
        """Extract relevant labels from Prometheus target"""
        labels = target.get('labels', {})
        return {
            'app_name': labels.get('app_name') or labels.get('service_name') or 'unknown',
            'app_type': labels.get('app_type') or 'generic',
            'job': labels.get('job') or labels.get('__name__', 'unknown'),
            'instance': labels.get('instance', 'unknown'),
            'container_name': labels.get('container_name') or labels.get('job', 'unknown'),
        }
    
    def should_create_dashboard(self, labels: Dict) -> bool:
        """Determine if dashboard should be created for this target"""
        # Only create for targets with app_name and app_type labels
        if not labels.get('app_name') or labels.get('app_name') == 'unknown':
            return False
        
        # Skip monitoring infrastructure itself
        skip_jobs = ['prometheus', 'node-exporter', 'cadvisor', 'loki', 'promtail']
        if labels.get('job') in skip_jobs:
            return False
        
        return True
    
    def create_dashboard_for_target(self, target: Dict, labels: Dict):
        """Create dashboard for a Prometheus target"""
        target_id = f"{labels['job']}:{labels['instance']}"
        
        # Skip if already processed
        if target_id in self.processed_targets:
            return
        
        # Check if dashboard already exists
        dashboard_title = f"{labels['app_name']} - {labels['app_type'].title()}"
        if self.grafana.dashboard_exists(dashboard_title):
            logger.debug(f"Dashboard already exists: {dashboard_title}")
            self.processed_targets.add(target_id)
            return
        
        # Get appropriate template
        template_name = self.template_manager.get_template_for_app_type(labels['app_type'])
        template = self.template_manager.load_template(template_name)
        
        if not template:
            logger.warning(f"No template found for {labels['app_type']}, skipping")
            return
        
        # Fill template with variables
        dashboard = self.template_manager.fill_template(template, {
            'app_name': labels['app_name'],
            'app_type': labels['app_type'],
            'job': labels['job'],
            'container_name': labels['container_name'],
            'instance': labels['instance'],
        })
        
        # Update dashboard metadata
        dashboard['title'] = dashboard_title
        dashboard['uid'] = f"{labels['app_name']}-{labels['app_type']}".lower().replace(' ', '-')
        dashboard['tags'] = [labels['app_type'], labels['app_name'], 'auto-generated']
        
        # Create dashboard
        if self.grafana.create_dashboard(dashboard):
            self.processed_targets.add(target_id)
            logger.info(f"Successfully created dashboard for {labels['app_name']}")
    
    def run_check(self):
        """Run one check cycle"""
        logger.info("Checking for new Prometheus targets...")
        
        targets = self.prometheus.get_active_targets()
        logger.info(f"Found {len(targets)} active targets")
        
        for target in targets:
            labels = self.extract_labels(target)
            
            if self.should_create_dashboard(labels):
                try:
                    self.create_dashboard_for_target(target, labels)
                except Exception as e:
                    logger.error(f"Error creating dashboard for {labels.get('app_name')}: {e}")
    
    def run(self):
        """Main loop"""
        logger.info("Starting Dashboard Automation Service")
        logger.info(f"Grafana URL: {GRAFANA_URL}")
        logger.info(f"Prometheus URL: {PROMETHEUS_URL}")
        logger.info(f"Check interval: {CHECK_INTERVAL}s")
        
        while True:
            try:
                self.run_check()
            except Exception as e:
                logger.error(f"Error in check cycle: {e}")
            
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    automation = DashboardAutomation()
    automation.run()


