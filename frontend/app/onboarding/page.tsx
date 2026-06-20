"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

// Types
type DiscoveredSubscription = {
  subscriptionId: string;
  displayName: string;
  state: string;
  tenantId: string;
};

type ValidationCheck = {
  name: string;
  mandatory: boolean;
  status: "passed" | "failed";
  message: string;
};

type TenantHealth = {
  subscriptionId: string;
  validationStatus: "passed" | "passed_with_warnings" | "failed";
  validationResults: Record<string, ValidationCheck>;
};

type SelectResult = {
  success: boolean;
  validationResults: TenantHealth[];
};

export default function Onboarding() {
  const router = useRouter();
  const [phase, setPhase] = useState<"welcome" | "discover" | "select" | "validate" | "poll">("welcome");
  const [subscriptions, setSubscriptions] = useState<DiscoveredSubscription[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [validationResults, setValidationResults] = useState<TenantHealth[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    // Check if they are already completed or polling
    api<{ status: string }>("/api/onboarding/status")
      .then(({ status }) => {
        if (status === "collecting" || status === "pending_collection") {
          setPhase("poll");
        } else if (status === "completed" || status === "ready") {
          router.push("/dashboard");
        }
      })
      .catch(console.error);
  }, [router]);

  useEffect(() => {
    if (phase !== "poll") return;
    const interval = setInterval(async () => {
      try {
        const { status } = await api<{ status: string }>("/api/onboarding/status");
        if (status === "completed" || status === "ready") {
          clearInterval(interval);
          router.push("/dashboard");
        }
      } catch (err) {
        console.error("Polling error", err);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [phase, router]);

  const handleDiscover = async () => {
    setPhase("discover");
    setError("");
    try {
      const data = await api<DiscoveredSubscription[]>("/api/onboarding/subscriptions/discover");
      setSubscriptions(data);
      setPhase("select");
    } catch (err) {
      setError(String(err));
      setPhase("welcome");
    }
  };

  const handleSelect = async () => {
    setPhase("validate");
    setError("");
    try {
      const data = await api<SelectResult>("/api/onboarding/subscriptions/select", undefined, {
        method: "POST",
        body: JSON.stringify({ subscriptionIds: Array.from(selectedIds) }),
      });
      setValidationResults(data.validationResults);
      if (data.success) {
        setPhase("poll");
      }
    } catch (err) {
      setError(String(err));
      setPhase("select");
    }
  };

  const toggleSelection = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedIds(newSet);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/30 p-4 relative">
      <div className="absolute top-4 right-4">
        <Button className="bg-transparent text-foreground border border-input hover:bg-accent hover:text-accent-foreground" onClick={() => window.location.href = "/api/auth/logout"}>Sign Out</Button>
      </div>
      <Card className="w-full max-w-2xl p-8 shadow-lg">
        <h1 className="mb-2 text-3xl font-bold tracking-tight">Welcome to Azure Cost Advisor</h1>
        <p className="mb-8 text-muted-foreground">Let's get your account set up by onboarding your Azure subscriptions.</p>

        {error && (
          <div className="mb-6 rounded-md bg-destructive/15 p-4 text-destructive">
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {phase === "welcome" && (
          <div className="flex flex-col items-center py-8">
            <p className="mb-6 text-center text-sm text-muted-foreground">
              We need to discover the Azure subscriptions you have access to. 
              Only active, enabled subscriptions will be shown.
            </p>
            <Button onClick={handleDiscover} className="px-8 py-3 text-lg">Discover Subscriptions</Button>
          </div>
        )}

        {phase === "discover" && (
          <div className="flex flex-col items-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-sm font-medium text-muted-foreground">Discovering subscriptions...</p>
          </div>
        )}

        {(phase === "select" || (phase === "validate" && validationResults.length > 0)) && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold">Select Subscriptions</h2>
            {subscriptions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No Azure subscriptions found for this account.</p>
            ) : (
              <div className="space-y-3 max-h-64 overflow-y-auto pr-2 border rounded-md p-4">
                {subscriptions.map(sub => (
                  <label key={sub.subscriptionId} className="flex items-start space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(sub.subscriptionId)}
                      onChange={() => toggleSelection(sub.subscriptionId)}
                      className="mt-1 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="text-sm font-medium">{sub.displayName}</p>
                      <p className="text-xs text-muted-foreground">{sub.subscriptionId}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}

            {validationResults.length > 0 && (
              <div className="mt-6 space-y-4 rounded-md bg-muted p-4">
                <h3 className="text-sm font-semibold">Validation Results</h3>
                {validationResults.map(health => (
                  <div key={health.subscriptionId} className="space-y-2">
                    <p className="text-xs font-medium uppercase text-muted-foreground">{health.subscriptionId}</p>
                    {Object.values(health.validationResults).map(check => (
                      <div key={check.name} className="flex items-start space-x-2 text-sm">
                        {check.status === "passed" ? (
                          <span className="text-green-600">✓</span>
                        ) : check.mandatory ? (
                          <span className="text-red-600">✗</span>
                        ) : (
                          <span className="text-amber-500">⚠</span>
                        )}
                        <div>
                          <span className="font-medium">{check.name}</span>
                          <span className="ml-2 text-xs text-muted-foreground">
                            ({check.mandatory ? "Required" : "Optional"})
                          </span>
                          <p className="text-xs text-muted-foreground mt-0.5">{check.message}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end space-x-4">
              {phase === "validate" && (
                <Button className="bg-transparent text-foreground border border-input hover:bg-accent hover:text-accent-foreground" onClick={() => setPhase("select")}>Back</Button>
              )}
              <Button 
                onClick={handleSelect} 
                disabled={selectedIds.size === 0 || phase === "validate"}
              >
                {phase === "validate" ? "Validating..." : "Validate & Continue"}
              </Button>
            </div>
          </div>
        )}

        {phase === "poll" && (
          <div className="flex flex-col items-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-base font-medium">Collecting Azure data...</p>
            <p className="mt-2 text-sm text-muted-foreground text-center">
              This may take a few moments depending on the size of your Azure environments.<br/>
              You will be automatically redirected when ready.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
