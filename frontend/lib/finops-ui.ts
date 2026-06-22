export type CurrencyAmount = {
  currency?: string;
  amount?: number;
  costAmount?: number;
};

export function formatMoney(
  amount?: number | null,
  currency = "INR",
  options: Intl.NumberFormatOptions = {},
) {
  const value = Number(amount ?? 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency || "INR",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
    ...options,
  }).format(value);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function freshnessLabel(value?: string | null, status?: string) {
  if (status && status !== "completed" && status !== "ready") {
    return { label: "Collection Failed", tone: "text-red-500 bg-red-500/10" };
  }
  if (!value) return { label: "Stale", tone: "text-amber-500 bg-amber-500/10" };
  const ageHours = (Date.now() - new Date(value).getTime()) / 36e5;
  if (ageHours <= 24) return { label: "Fresh", tone: "text-emerald-500 bg-emerald-500/10" };
  return { label: "Stale", tone: "text-amber-500 bg-amber-500/10" };
}

export function classifyService(service = "") {
  const text = service.toLowerCase();
  if (/(virtual machines|compute|aks|kubernetes|app service|container)/.test(text)) return "Compute";
  if (/(gateway|bandwidth|virtual network|public ip|nat|dns|load balancer)/.test(text)) return "Networking";
  if (/(storage|disk|backup)/.test(text)) return "Storage";
  if (/(sql|postgres|mysql|database|cosmos|redis)/.test(text)) return "Databases";
  if (/(openai|cognitive|search|ai|machine learning)/.test(text)) return "AI Services";
  return "Other";
}

export function riskFor(category = "", savings = 0) {
  const text = category.toLowerCase();
  if (text.includes("public_ip") || text.includes("idle")) return "Low";
  if (text.includes("aks") || text.includes("compute") || savings > 300) return "Low to Medium";
  return "Medium";
}

export function recommendationTitle(row: { title?: string; category?: string; resourceId?: string }) {
  const category = (row.category || "").toLowerCase();
  if (category.includes("idle_public_ip")) return "Unused Public IP Detected";
  if (category.includes("aks")) return "AKS Cluster Overprovisioned";
  if (category.includes("rightsizing")) return "Rightsizing Opportunity";
  return humanize(row.title || category || "Optimization Opportunity");
}

export function humanize(value = "") {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function recommendationNarrative(row: {
  category?: string;
  content?: string;
  evidence?: Record<string, unknown>;
  estimatedSavings?: number;
}) {
  const category = (row.category || "").toLowerCase();
  if (category.includes("idle_public_ip")) {
    return {
      why: "This public IP has not been associated with an active workload during the analysis period.",
      impact: "You are paying for a resource that is not actively serving traffic.",
      action: "Delete the public IP if it is no longer required, or associate it with an active workload.",
    };
  }
  if (category.includes("aks")) {
    const cpu = row.evidence?.cpuAverage ?? row.evidence?.cpu_avg_percent;
    return {
      why: `Average utilization is low${cpu ? ` at approximately ${Number(cpu).toFixed(1)}% CPU` : ""}.`,
      impact: "Compute capacity appears overprovisioned compared with observed workload demand.",
      action: "Enable Cluster Autoscaler, review node pool sizing, or reduce node count after validating workload requirements.",
    };
  }
  return {
    why: row.content || "The platform identified a spend optimization opportunity from collected Azure data.",
    impact: "Addressing this recommendation may reduce recurring Azure spend or improve governance.",
    action: row.content || "Review the resource owner and apply the suggested optimization.",
  };
}
