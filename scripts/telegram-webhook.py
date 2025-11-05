#!/usr/bin/env python3
"""
Telegram Webhook for Alertmanager
Receives alerts from Alertmanager and forwards them to Telegram
"""

import os
import json
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'


def send_telegram_message(text, parse_mode='Markdown'):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured")
        return False
    
    try:
        response = requests.post(
            TELEGRAM_API_URL,
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': parse_mode
            },
            timeout=10
        )
        response.raise_for_status()
        logger.info("Message sent to Telegram successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def format_alert_message(alert_data):
    """Format alert data into Telegram message"""
    alerts = alert_data.get('alerts', [])
    group_labels = alert_data.get('groupLabels', {})
    common_labels = alert_data.get('commonLabels', {})
    
    alertname = group_labels.get('alertname', 'Unknown Alert')
    severity = common_labels.get('severity', 'unknown')
    
    # Emoji based on severity
    emoji_map = {
        'critical': '🚨',
        'warning': '⚠️',
        'info': 'ℹ️'
    }
    emoji = emoji_map.get(severity.lower(), '🔔')
    
    message = f"{emoji} *{alertname}*\n\n"
    
    if severity:
        message += f"*Severity:* {severity.upper()}\n"
    
    for alert in alerts:
        status = alert.get('status', 'unknown')
        labels = alert.get('labels', {})
        annotations = alert.get('annotations', {})
        
        message += f"\n*Status:* {status.upper()}\n"
        
        if labels.get('service_name'):
            message += f"*Service:* {labels['service_name']}\n"
        elif labels.get('job'):
            message += f"*Service:* {labels['job']}\n"
        
        if labels.get('instance'):
            message += f"*Instance:* {labels['instance']}\n"
        
        if labels.get('container_name'):
            message += f"*Container:* {labels['container_name']}\n"
        
        if annotations.get('summary'):
            message += f"\n*Summary:*\n{annotations['summary']}\n"
        
        if annotations.get('description'):
            message += f"\n*Description:*\n{annotations['description']}\n"
        
        if alert.get('startsAt'):
            message += f"\n*Started:* {alert['startsAt']}\n"
        
        if alert.get('endsAt') and status == 'resolved':
            message += f"*Resolved:* {alert['endsAt']}\n"
    
    return message


class AlertHandler(BaseHTTPRequestHandler):
    """HTTP handler for Alertmanager webhooks"""
    
    def do_POST(self):
        """Handle POST requests from Alertmanager"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            alert_data = json.loads(post_data.decode('utf-8'))
            
            logger.info(f"Received alert: {alert_data.get('groupLabels', {}).get('alertname', 'unknown')}")
            
            # Format and send message
            message = format_alert_message(alert_data)
            success = send_telegram_message(message)
            
            if success:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': 'Failed to send to Telegram'}).encode())
        
        except Exception as e:
            logger.error(f"Error processing alert: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode())
    
    def do_GET(self):
        """Health check endpoint"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'status': 'ok',
            'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        }).encode())
    
    def log_message(self, format, *args):
        """Override to use logger instead of print"""
        logger.info(f"{self.address_string()} - {format % args}")


def main():
    """Main function"""
    port = int(os.getenv('PORT', '8080'))
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️  Telegram credentials not configured!")
        logger.warning("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
    
    server = HTTPServer(('0.0.0.0', port), AlertHandler)
    logger.info(f"🚀 Telegram webhook server started on port {port}")
    logger.info(f"📡 Listening for alerts from Alertmanager...")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()


if __name__ == '__main__':
    main()


