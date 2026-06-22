"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type DiscoveredSubscription = {
  subscriptionId: string;
  displayName: string;
  state: string;
  tenantId: string;
};

type ValidationCheck = {
  name: string;
  mandatory: boolean;
  status: "passed" | "failed" | "error";
  message: string;
  httpStatus?: number;
  requiredPermission?: string;
  whyRequired?: string;
  approvalUrl?: string;
  approver?: string;
};

type TenantHealth = {
  subscriptionId: string;
  validationStatus: "passed" | "passed_with_warnings" | "failed";
  validationResults: Record<string, ValidationCheck>;
};

type SelectResult = {
  success: boolean;
  message?: string;
  validationResults: TenantHealth[];
};

type OnboardingStatus = {
  status: string;
  message?: string;
  errors?: string[];
  validationResults?: TenantHealth[];
};

type Phase = "welcome" | "discover" | "select" | "validate" | "permissions" | "poll";

export default function Onboarding() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("welcome");
  const [subscriptions, setSubscriptions] = useState<DiscoveredSubscription[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [validationResults, setValidationResults] = useState<TenantHealth[]>([]);
  const [error, setError] = useState<string>("");
  const [collectionErrors, setCollectionErrors] = useState<string[]>([]);

  useEffect(() => {
    api<OnboardingStatus>("/api/onboarding/status")
      .then(({ status, message, errors, validationResults }) => {
        if (status === "collecting" || status === "pending_collection") {
          setPhase("poll");
        } else if (status === "ready") {
          router.push("/dashboard");
        } else if (status === "collection_failed") {
          setCollectionErrors(errors || []);
          setError(message || "Collection failed");
          setPhase("poll");
        } else if (status === "permission_validation_failed" || status === "permission_validation_required") {
          const results = validationResults || [];
          setValidationResults(results);
          setSelectedIds(new Set(results.map((item) => item.subscriptionId)));
          setError(message || "Required Azure permissions are missing.");
          setPhase("permissions");
        }
      })
      .catch(console.error);
  }, [router]);

  useEffect(() => {
    if (phase !== "poll") return;
    const interval = setInterval(async () => {
      try {
        const { status, message, errors } = await api<OnboardingStatus>("/api/onboarding/status");
        if (status === "ready") {
          clearInterval(interval);
          router.push("/dashboard");
        } else if (status === "collection_failed") {
          clearInterval(interval);
          setCollectionErrors(errors || []);
          setError(message || "Collection failed");
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
        setCollectionErrors([]);
        setPhase("poll");
      } else {
        setError(data.message || "Required Azure permissions are missing. Collection has not started.");
        setPhase("permissions");
      }
    } catch (err) {
      setError(String(err));
      setPhase(subscriptions.length > 0 ? "select" : "permissions");
    }
  };

  const handleRetryCollection = async () => {
    setError("");
    setCollectionErrors([]);
    setPhase("poll");
    try {
      await api("/api/onboarding/collection/retry", undefined, { method: "POST" });
    } catch (err) {
      setError(String(err));
    }
  };

  const toggleSelection = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-3xl p-8 shadow-lg">
        <h1 className="mb-2 text-3xl font-bold tracking-tight">Welcome to FinsOpsIQ</h1>
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
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            <p className="mt-4 text-sm font-medium text-muted-foreground">Discovering subscriptions...</p>
          </div>
        )}

        {(phase === "select" || phase === "validate" || phase === "permissions") && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold">
                {phase === "permissions" ? "Permission status" : "Select subscriptions"}
              </h2>
              {phase === "permissions" && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Collection will start only after every required Azure permission is granted for the selected subscription.
                </p>
              )}
            </div>

            {subscriptions.length === 0 && phase !== "permissions" ? (
              <p className="text-sm text-muted-foreground">No Azure subscriptions found for this account.</p>
            ) : subscriptions.length > 0 ? (
              <div className="max-h-64 space-y-3 overflow-y-auto rounded-md border p-4 pr-2">
                {subscriptions.map((sub) => (
                  <label key={sub.subscriptionId} className="flex cursor-pointer items-start space-x-3">
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
            ) : null}

            {phase === "validate" && validationResults.length === 0 && (
              <div className="flex flex-col items-center rounded-md border p-8">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <p className="mt-4 text-sm font-medium text-muted-foreground">Validating Azure permissions...</p>
              </div>
            )}

            {validationResults.length > 0 && (
              <div className="space-y-4 rounded-md border bg-muted/40 p-4">
                <h3 className="text-sm font-semibold">Required permissions</h3>
                {validationResults.map((health) => (
                  <div key={health.subscriptionId} className="space-y-3 rounded-md bg-background p-4">
                    <div>
                      <p className="text-xs font-medium uppercase text-muted-foreground">Subscription</p>
                      <p className="text-sm font-medium">{health.subscriptionId}</p>
                    </div>
                    {Object.values(health.validationResults).map((check) => {
                      const granted = check.status === "passed";
                      return (
                        <div key={check.name} className="rounded-md border p-3 text-sm">
                          <div className="flex items-start space-x-2">
                            <span className={granted ? "text-green-600" : "text-red-600"}>
                              {granted ? "✓" : "✕"}
                            </span>
                            <div className="flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium">{check.requiredPermission || check.name}</span>
                                <span className={`rounded-full px-2 py-0.5 text-xs ${granted ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                                  {granted ? "Granted" : "Missing"}
                                </span>
                                {check.httpStatus && (
                                  <span className="text-xs text-muted-foreground">HTTP {check.httpStatus}</span>
                                )}
                              </div>
                              {check.whyRequired && (
                                <p className="mt-1 text-xs text-muted-foreground">{check.whyRequired}</p>
                              )}
                              <p className="mt-1 text-xs text-muted-foreground">{check.message}</p>
                              {!granted && check.approver && (
                                <p className="mt-2 text-xs text-muted-foreground">{check.approver}</p>
                              )}
                              {!granted && check.approvalUrl && (
                                <a
                                  href={check.approvalUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="mt-2 inline-flex text-xs font-medium text-primary underline"
                                >
                                  Open Microsoft approval page
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end space-x-4">
              {(phase === "validate" || phase === "permissions") && subscriptions.length > 0 && (
                <Button className="border border-input bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground" onClick={() => setPhase("select")}>
                  Back
                </Button>
              )}
              <Button onClick={handleSelect} disabled={selectedIds.size === 0 || phase === "validate"}>
                {phase === "validate" ? "Validating..." : phase === "permissions" ? "Re-check permissions" : "Validate & Continue"}
              </Button>
            </div>
          </div>
        )}

        {phase === "poll" && (
          <div className="flex flex-col items-center py-12">
            {error ? (
              <>
                <div className="mb-4 w-full rounded-md bg-destructive/15 p-4 text-destructive">
                  <p className="text-base font-semibold">Collection failed</p>
                  <p className="mt-1 text-sm">{error}</p>
                  {collectionErrors.length > 0 && (
                    <ul className="mt-3 list-disc space-y-1 pl-5 text-xs">
                      {collectionErrors.map((item, index) => (
                        <li key={`${index}-${item}`}>{item}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <Button onClick={handleRetryCollection}>Retry collection</Button>
              </>
            ) : (
              <>
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <p className="mt-4 text-base font-medium">Collecting Azure data...</p>
                <p className="mt-2 text-center text-sm text-muted-foreground">
                  This may take a few moments depending on the size of your Azure environments.<br />
                  You will be automatically redirected when collection is complete.
                </p>
              </>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
