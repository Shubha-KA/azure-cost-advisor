# AI-Powered Azure Cost Optimization Advisor

An enterprise-grade FinOps application that collects and analyzes Azure cost and utilization data, runs mathematical and heuristic algorithms to identify waste and anomalies, and feeds results into an AI-powered conversational dashboard (RAG using LangChain and FAISS).

---

## 1. Networking Architecture (Hub-and-Spoke)

For enterprise security, the application deploys inside a private, secure **Hub-and-Spoke network topology** in Azure:

```mermaid
flowchart TD
    subgraph Internet ["Internet (Public)"]
        User["User Web Browser"]
    end

    subgraph HubVNet ["Hub Virtual Network (10.0.0.0/16)"]
        subgraph AppGwSubnet ["App Gateway Subnet (10.0.1.0/24)"]
            AppGw["Application Gateway WAF_v2 (Port 80)"]
        end
        NSG_Hub["NSG: Restricts traffic to 80/443 & GatewayManager"]
    end

    subgraph Peering ["VNet Peering (Bidirectional)"]
        Peer["Low-Latency Peering Connection"]
    end

    subgraph SpokeVNet ["Spoke Virtual Network (10.1.0.0/16)"]
        subgraph CASubnet ["Container Apps Subnet (10.1.0.0/23)"]
            CAE["Container Apps Environment (Internal Load Balancer)"]
            Streamlit["Streamlit Dashboard App (Port 8501)"]
        end
        NSG_Spoke["NSG: Inbound 8501 only from Hub, Outbound 443 only to Internet"]
    end

    User -->|Public HTTP| AppGw
    AppGwSubnet --> Peering
    Peering --> CASubnet
    AppGw -->|Private Routing (Port 8501)| Streamlit
```

### Security Details:
- **Public Entry**: The **Application Gateway WAF_v2** is the only public-facing resource, routing public HTTP (port 80) traffic safely to the backend. It runs in WAF Prevention Mode with the OWASP 3.2 ruleset.
- **Private Compute**: The Streamlit App runs in the **Spoke VNet** inside a **Container Apps Environment** configured with an **Internal Load Balancer (ILB)**. The environment subnet (`snet-containerapps`) is delegated to `Microsoft.App/environments`. It has no public IP and is inaccessible from the public internet.
- **VNet Peering**: Enables the Application Gateway in the Hub to route traffic privately to the Container App in the Spoke with single-digit millisecond latency.
- **NSG Protection**: Strictly controls traffic flows. Inbound to the Spoke VNet is restricted exclusively to requests on port `8501` originating from the Hub VNet's CIDR range. Outbound traffic is locked down to HTTPS (port `443`) for secure external API calls.

For a deeper dive into the system design, data flows, and processing pipelines, see [architecture.md](file:///c:/Users/shubh/OneDrive/Desktop/AI-Cost-Optimizer/azure-cost-advisor/architecture.md).

---

## 2. Setup Instructions

The application requires Python 3.11.

### Option A: Local Demo Mode (No-Configuration Offline Fallback)
If no Azure or OpenAI credentials are provided, the application automatically falls back to an offline simulated engine with comprehensive mock datasets. This allows you to run, test, and experience the complete system instantly without an active subscription.

### Option B: Enterprise Connected Mode
1. **Initialize the local virtual environment**:
   ```bash
   python -m venv .venv
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   # Linux/macOS
   source .venv/bin/activate
   ```

2. **Install all requirements**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill out your Azure and OpenAI configuration:
   ```bash
   cp .env.example .env
   ```
   *Required variables for Azure collection:* `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
   *Required variables for AI features:* `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`.

4. **Run the data collection and analysis pipeline**:
   ```bash
   python -m src.pipeline
   ```
   *If you want to run calculations without setting up Azure OpenAI, skip the AI embeddings compilation:*
   ```bash
   python -m src.pipeline --skip-ai
   ```

5. **Start the Streamlit dashboard**:
   ```bash
   streamlit run src/dashboard/app.py
   ```
   Open `http://localhost:8501` in your browser.

---

## 3. Local Testing

All modules are guarded by a robust test suite covering collectors, processing heuristics, anomaly z-scores, RAG vector stores, and CLI pipelines.

We use `pytest` along with `pytest-cov` to run unit tests and produce coverage reports:

```bash
# Run the complete test suite with detailed output
pytest tests/ -v

# Run the test suite and output terminal code coverage report
pytest tests/ -v --cov=src --cov-report=term-missing
```

The tests run entirely locally using pre-packaged mock data configurations inside [tests/mock_data/](file:///c:/Users/shubh/OneDrive/Desktop/AI-Cost-Optimizer/azure-cost-advisor/tests/mock_data).

---

## 4. Docker Usage

You can containerize the application to ensure clean, isolated, and repeatable execution across environments.

### Dockerfile
The application uses a multi-stage Docker build (`Dockerfile`) to produce lightweight and highly secure production-ready images:
- **Build image**:
  ```bash
  docker build -t azure-cost-advisor:latest .
  ```
- **Run container**:
  ```bash
  docker run -d -p 8501:8501 --env-file .env --name cost-advisor azure-cost-advisor:latest
  ```

### Docker Compose
We use Docker Compose to manage local development environments matching the Azure Container App specs:
- **Build and start services in the background**:
  ```bash
  docker compose up -d --build
  ```
- **View logs**:
  ```bash
  docker compose logs -f
  ```
- **Stop and remove container resources**:
  ```bash
  docker compose down
  ```

---

## 5. Terraform Deployment

To deploy the entire networking topology, Application Gateway, and containerized runtime in Azure, we use Terraform.

1. **Move to the infra directory**:
   ```bash
   cd infra
   ```

2. **Configure your Variables**:
   Copy `terraform.tfvars.example` to `terraform.tfvars` and customize your values:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
   Set your customized registry path in `docker_image` (e.g. `myregistry.azurecr.io/azure-cost-advisor:latest`) and supply OpenAI credentials if needed.

3. **Deploy using CLI**:
   ```bash
   # Initialize Terraform provider plugins
   terraform init

   # Dry-run validation to view planned infrastructure
   terraform plan

   # Provision resources in Azure
   terraform apply
   ```

4. **Outputs**:
   Once applied, Terraform exposes the public Application Gateway address:
   - `application_gateway_public_ip`
   - `dashboard_url` (accessible on `http://<public-ip>`)

---

## 6. CI/CD Pipelines (Azure DevOps)

The application includes two decoupled YAML pipeline configurations inside the [pipelines/](file:///c:/Users/shubh/OneDrive/Desktop/AI-Cost-Optimizer/azure-cost-advisor/pipelines) directory:

### CI Build Pipeline ([build.yml](file:///c:/Users/shubh/OneDrive/Desktop/AI-Cost-Optimizer/azure-cost-advisor/pipelines/build.yml))
- **Triggers**: Automatically runs on every merge or direct commit to the `main` branch.
- **Actions**:
  1. Installs Python 3.11 and upgrades `pip`.
  2. Installs requirements listed in `requirements.txt`.
  3. Executes the full `pytest` suite, producing a JUnit test results report and detailed code coverage files.
  4. Publishes test results and coverage data directly to the Azure DevOps build run dashboard.
  5. Compiles and tags the Docker image with the dynamic `BuildId`.
  6. Pushes the Docker image to the Azure Container Registry (ACR) service connection (`cost-advisor-acr-service-connection`).

### CD Deploy Pipeline ([deploy.yml](file:///c:/Users/shubh/OneDrive/Desktop/AI-Cost-Optimizer/azure-cost-advisor/pipelines/deploy.yml))
- **Triggers**: Automatically triggers upon a successful execution run of the `build.yml` pipeline.
- **Actions**:
  1. Installs the specific version of Terraform.
  2. Authenticates securely against Azure RM via the configured service connection (`azure-cost-advisor-service-connection`).
  3. Performs `terraform init` and compiles a dry-run `terraform plan`, generating an immutable plan file (`tfplan`) using the newly compiled Docker image tag.
  4. Runs `terraform apply` to safely provision and deploy changes to the Resource Group, VNets, and Container Runtime.
  5. Executes a secure CLI validation step checking the Application Gateway's backend pools and confirming appropriate private routing across peered subnets.
