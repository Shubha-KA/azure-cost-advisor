"""Delegated Azure subscription discovery and API access validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from pydantic import BaseModel, Field

ARM_ENDPOINT = "https://management.azure.com"


class AzureAccessError(RuntimeError):
    pass


class DiscoveredSubscription(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    display_name: str = Field(alias="displayName")
    state: str = "Unknown"
    tenant_id: str = Field(default="", alias="tenantId")

    model_config = {"populate_by_name": True}


class ValidationCheck(BaseModel):
    name: str
    status: str
    mandatory: bool
    message: str
    http_status: int | None = Field(default=None, alias="httpStatus")
    required_permission: str = Field(default="", alias="requiredPermission")
    why_required: str = Field(default="", alias="whyRequired")
    approval_url: str = Field(default="", alias="approvalUrl")
    approver: str = ""

    model_config = {"populate_by_name": True}


@dataclass
class AzureAccessClient:
    access_token: str
    http: Any = requests
    timeout: int = 30

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def discover_subscriptions(self) -> list[DiscoveredSubscription]:
        response = self.http.get(
            f"{ARM_ENDPOINT}/subscriptions",
            params={"api-version": "2022-12-01"},
            headers=self.headers,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise AzureAccessError(
                f"Subscription discovery failed ({response.status_code}): "
                f"{_response_message(response)}"
            )
        return [
            DiscoveredSubscription(
                subscriptionId=item["subscriptionId"],
                displayName=item.get("displayName", item["subscriptionId"]),
                state=item.get("state", "Unknown"),
                tenantId=item.get("tenantId", ""),
            )
            for item in response.json().get("value", [])
        ]

    def validate_subscription(
        self, subscription_id: str
    ) -> dict[str, ValidationCheck]:
        scope = f"/subscriptions/{subscription_id}"
        approval_url = (
            "https://portal.azure.com/#view/Microsoft_Azure_IAM/"
            f"AccessControlMenuBlade/~/roleAssignments/scope/{scope}"
        )
        return {
            "authentication": ValidationCheck(
                name="Authentication",
                status="passed" if self.access_token else "failed",
                mandatory=True,
                message="Delegated ARM token is available"
                if self.access_token
                else "No delegated ARM token is available",
                requiredPermission="Microsoft Entra sign-in",
                whyRequired="The platform needs a delegated Azure Resource Manager token before it can validate subscription access.",
                approvalUrl="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
                approver="A Microsoft Entra administrator or application administrator can approve application consent if your tenant requires it.",
            ),
            "subscriptionAccess": self._check(
                "Reader",
                True,
                "GET",
                f"{ARM_ENDPOINT}{scope}/resources",
                params={"api-version": "2021-04-01", "$top": 1},
                required_permission="Reader",
                why_required="Required to discover Azure resources and correlate inventory with cost and recommendations.",
                approval_url=approval_url,
                approver="A subscription Owner or User Access Administrator can assign Reader on this subscription.",
            ),
            "costManagement": self._check(
                "Cost Management Reader",
                True,
                "POST",
                f"{ARM_ENDPOINT}{scope}/providers/Microsoft.CostManagement/query",
                params={"api-version": "2023-11-01"},
                json={
                    "type": "ActualCost",
                    "timeframe": "MonthToDate",
                    "dataset": {
                        "granularity": "None",
                        "aggregation": {
                            "totalCost": {
                                "name": "PreTaxCost",
                                "function": "Sum",
                            }
                        },
                    },
                },
                required_permission="Cost Management Reader",
                why_required="Required to read cost and usage records used for spend analytics, top-cost resources, and savings calculations.",
                approval_url=approval_url,
                approver="A subscription Owner, Cost Management administrator, or User Access Administrator can assign Cost Management Reader.",
            ),
            "resourceGraph": self._check(
                "Resource Graph access",
                True,
                "POST",
                f"{ARM_ENDPOINT}/providers/Microsoft.ResourceGraph/resources",
                params={"api-version": "2022-10-01"},
                json={
                    "subscriptions": [subscription_id],
                    "query": "Resources | project id | take 1",
                    "options": {"resultFormat": "objectArray"},
                },
                required_permission="Resource Graph access",
                why_required="Required to query Azure Resource Graph for subscription-wide resource inventory during collection.",
                approval_url=approval_url,
                approver="A subscription Owner or User Access Administrator should ensure Reader access is assigned; Resource Graph is accessed through Azure Resource Manager.",
            ),
            "advisor": self._check(
                "Advisor Reader",
                True,
                "GET",
                f"{ARM_ENDPOINT}{scope}/providers/Microsoft.Advisor/recommendations",
                params={"api-version": "2023-01-01", "$top": 1},
                required_permission="Advisor Reader",
                why_required="Required to read Azure Advisor recommendations and convert them into actionable optimization guidance.",
                approval_url=approval_url,
                approver="A subscription Owner or User Access Administrator can assign Advisor Reader on this subscription.",
            ),
            "monitor": self._check(
                "Monitoring Reader",
                True,
                "GET",
                f"{ARM_ENDPOINT}{scope}/providers/Microsoft.Insights/metricAlerts",
                params={"api-version": "2018-03-01"},
                required_permission="Monitoring Reader",
                why_required="Required to read Azure Monitor configuration and metrics used for utilization and underused-resource analysis.",
                approval_url=approval_url,
                approver="A subscription Owner or User Access Administrator can assign Monitoring Reader on this subscription.",
            ),
        }

    def _check(
        self,
        name: str,
        mandatory: bool,
        method: str,
        url: str,
        required_permission: str = "",
        why_required: str = "",
        approval_url: str = "",
        approver: str = "",
        **kwargs: Any,
    ) -> ValidationCheck:
        try:
            response = self.http.request(
                method,
                url,
                headers=self.headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            return ValidationCheck(
                name=name,
                status="error",
                mandatory=mandatory,
                message=f"Azure request failed: {exc}",
                requiredPermission=required_permission,
                whyRequired=why_required,
                approvalUrl=approval_url,
                approver=approver,
            )
        if 200 <= response.status_code < 300:
            return ValidationCheck(
                name=name,
                status="passed",
                mandatory=mandatory,
                message="Access verified",
                httpStatus=response.status_code,
                requiredPermission=required_permission,
                whyRequired=why_required,
                approvalUrl=approval_url,
                approver=approver,
            )
        if response.status_code in (401, 403):
            message = (
                "Authentication was rejected"
                if response.status_code == 401
                else f"Missing {'required' if mandatory else 'optional'} Azure access"
            )
        else:
            message = f"Azure API returned: {_response_message(response)}"
        return ValidationCheck(
            name=name,
            status="failed",
            mandatory=mandatory,
            message=message,
            httpStatus=response.status_code,
            requiredPermission=required_permission,
            whyRequired=why_required,
            approvalUrl=approval_url,
            approver=approver,
        )


def _response_message(response) -> str:
    try:
        payload = response.json()
        error = payload.get("error", payload)
        return str(error.get("message", error)) if isinstance(error, dict) else str(error)
    except Exception:
        return str(getattr(response, "text", "Unknown Azure error"))[:500]
