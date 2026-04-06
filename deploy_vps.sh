#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# HIVE MIND ALPHA — VPS Deployment Script (Tier 1)
# Run this on a fresh Ubuntu 22.04 VPS (DigitalOcean/Linode/AWS)
# Cost: ~₹600–1,200/month for 2GB RAM droplet
# ═══════════════════════════════════════════════════════════════

set -e

echo "=== HIVE MIND ALPHA — VPS Setup ==="

# 1. System update
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv git screen ufw

# 2. Firewall — only allow SSH + Streamlit port
sudo ufw allow 22/tcp
sudo ufw allow 8501/tcp
sudo ufw --force enable

# 3. Clone repo
cd /home/$USER
git clone https://github.com/dinumathew/hivemind-alpha.git
cd hivemind-alpha

# 4. Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create secrets file (edit this with your actual keys)
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'SECRETS'
ANTHROPIC_API_KEY  = "sk-ant-YOUR_KEY"
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID   = "YOUR_CHAT_ID"
GROWW_API_TOKEN    = "YOUR_GROWW_TOKEN"
APP_USERNAME       = "dinu"
APP_PASSWORD       = "YOUR_STRONG_PASSWORD"
SECRETS

echo "=== Edit .streamlit/secrets.toml with your actual keys ==="

# 6. Create systemd service for auto-restart on reboot
sudo bash -c "cat > /etc/systemd/system/hivemind.service << 'SERVICE'
[Unit]
Description=Hive Mind Alpha Trading Intelligence
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/hivemind-alpha
ExecStart=/home/$USER/hivemind-alpha/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE"

sudo systemctl daemon-reload
sudo systemctl enable hivemind
sudo systemctl start hivemind

# 7. Verify
sleep 5
sudo systemctl status hivemind --no-pager

echo ""
echo "=== DEPLOYMENT COMPLETE ==="
echo "App running at: http://$(curl -s ifconfig.me):8501"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status hivemind   # Check status"
echo "  sudo systemctl restart hivemind  # Restart app"
echo "  sudo journalctl -u hivemind -f   # Live logs"
echo "  cd hivemind-alpha && git pull && sudo systemctl restart hivemind  # Update"
