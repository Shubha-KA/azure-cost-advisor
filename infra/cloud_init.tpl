#cloud-config
# =============================================================================
# Cloud-init — Azure Cost Advisor (Streamlit)
# Runs on first boot of each VMSS instance
# =============================================================================

package_update: true
package_upgrade: true

packages:
  - python3
  - python3-pip
  - python3-venv
  - git
  - curl

write_files:
  # ── Systemd service ────────────────────────────────────────────────────────
  - path: /etc/systemd/system/streamlit.service
    owner: root:root
    permissions: "0644"
    content: |
      [Unit]
      Description=Azure Cost Advisor — Streamlit Dashboard
      After=network-online.target
      Wants=network-online.target

      [Service]
      Type=simple
      User=streamlit
      WorkingDirectory=/opt/cost-advisor
      EnvironmentFile=/opt/cost-advisor/.env
      ExecStart=/opt/cost-advisor/venv/bin/streamlit run src/dashboard/app.py \
                  --server.port=${streamlit_port} \
                  --server.address=0.0.0.0 \
                  --server.headless=true \
                  --server.enableCORS=false
      Restart=always
      RestartSec=10
      StandardOutput=journal
      StandardError=journal

      [Install]
      WantedBy=multi-user.target

  # ── Environment file (secrets injected by Terraform templatefile) ──────────
  - path: /opt/cost-advisor/.env
    owner: streamlit:streamlit
    permissions: "0600"
    content: |
      AZURE_OPENAI_ENDPOINT=${azure_openai_endpoint}
      AZURE_OPENAI_API_KEY=${azure_openai_api_key}
      AZURE_OPENAI_DEPLOYMENT_NAME=${azure_openai_deployment_name}
      AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${azure_openai_embedding}
      AZURE_OPENAI_API_VERSION=${azure_openai_api_version}
      DATA_RAW_DIR=/opt/cost-advisor/data/raw
      DATA_PROCESSED_DIR=/opt/cost-advisor/data/processed
      DATA_EMBEDDINGS_DIR=/opt/cost-advisor/data/embeddings
      STREAMLIT_SERVER_PORT=${streamlit_port}

runcmd:
  # ── Create service user ────────────────────────────────────────────────────
  - useradd --system --shell /bin/false --home /opt/cost-advisor streamlit

  # ── Clone application ──────────────────────────────────────────────────────
  - git clone https://github.com/your-org/azure-cost-advisor.git /opt/cost-advisor
  - chown -R streamlit:streamlit /opt/cost-advisor

  # ── Create Python venv and install deps ───────────────────────────────────
  - sudo -u streamlit python3 -m venv /opt/cost-advisor/venv
  - sudo -u streamlit /opt/cost-advisor/venv/bin/pip install --upgrade pip
  - sudo -u streamlit /opt/cost-advisor/venv/bin/pip install -r /opt/cost-advisor/azure-cost-advisor/requirements.txt

  # ── Create data directories ────────────────────────────────────────────────
  - mkdir -p /opt/cost-advisor/data/{raw,processed,embeddings}
  - chown -R streamlit:streamlit /opt/cost-advisor/data

  # ── Enable and start service ───────────────────────────────────────────────
  - systemctl daemon-reload
  - systemctl enable streamlit
  - systemctl start streamlit
