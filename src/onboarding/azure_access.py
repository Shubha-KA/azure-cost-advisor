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
        return {
            "authentication": ValidationCheck(
                name="Authentication",
                status="passed" if self.access_token else "failed",
                mandatory=True,
                message="Delegated ARM token is available"
                if self.access_token
                else "No delegated ARM token is available",
            ),
            "subscriptionAccess": self._check(
                "Subscription access (Reader)",
                True,
                "GET",
                f"{ARM_ENDPOINT}{scope}",
                params={"api-version": "2022-12-01"},
            ),
            "costManagement": self._check(
                "Cost Management access",
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
            ),
            "advisor": self._check(
                "Azure Advisor access",
                False,
                "GET",
                f"{ARM_ENDPOINT}{scope}/providers/Microsoft.Advisor/recommendations",
                params={"api-version": "2023-01-01", "$top": 1},
            ),
            "monitor": self._check(
                "Azure Monitor access",
                False,
                "GET",
                f"{ARM_ENDPOINT}{scope}/providers/Microsoft.Insights/metricAlerts",
                params={"api-version": "2018-03-01"},
            ),
        }

    def _check(
        self,
        name: str,
        mandatory: bool,
        method: str,
        url: str,
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
            )
        if 200 <= response.status_code < 300:
            return ValidationCheck(
                name=name,
                status="passed",
                mandatory=mandatory,
                message="Access verified",
                httpStatus=response.status_code,
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
        )


def _response_message(response) -> str:
    try:
        payload = response.json()
        error = payload.get("error", payload)
        return str(error.get("message", error)) if isinstance(error, dict) else str(error)
    except Exception:
        return str(getattr(response, "text", "Unknown Azure error"))[:500]
