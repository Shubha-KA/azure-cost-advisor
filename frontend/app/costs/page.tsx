"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { classifyService, formatMoney } from "@/lib/finops-ui";
import { useScope } from "@/components/scope-provider";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page";
import { ChartSkeleton, TableSkeleton } from "@/components/ux";

type CostRow = {
  date?: string;
  period?: string;
  service_name?: string;
  resource_group?: string;
  currency: string;
  costAmount: number;
};
type Resource = {
  resourceName: string;
  resourceGroup: string;
  estimatedMonthlyCost?: number;
  estimatedSavings?: number;
  estimatedCostCurrency?: string;
  savingsCurrency?: string;
};
type Recommendation = { estimatedSavings?: number; currency?: string };

const COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

export default function Costs() {
  const { scope } = useScope();
  const [trends, setTrends] = useState<CostRow[]>([]);
  const [monthly, setMonthly] = useState<CostRow[]>([]);
  const [services, setServices] = useState<CostRow[]>([]);
  const [groups, setGroups] = useState<CostRow[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!scope.subscriptionId) return;
    setLoading(true);
    Promise.all([
      api<CostRow[]>("/api/costs/trends", scope),
      api<CostRow[]>("/api/costs/trends?granularity=monthly", scope),
      api<CostRow[]>("/api/costs/services", scope),
      api<CostRow[]>("/api/costs/resource-groups", scope),
      api<Resource[]>("/api/resources", scope),
      api<Recommendation[]>("/api/recommendations", scope),
    ])
      .then(([daily, monthlyRows, serviceRows, groupRows, resourceRows, recs]) => {
        setTrends(daily);
        setMonthly(monthlyRows);
        setServices(serviceRows);
        setGroups(groupRows);
        setResources(resourceRows);
        setRecommendations(recs);
      })
      .finally(() => setLoading(false));
  }, [scope]);

  const currency = trends[0]?.currency || services[0]?.currency || "INR";
  const weekly = useMemo(() => toWeekly(trends), [trends]);
  const serviceSpend = useMemo(
    () => [...services].sort((a, b) => b.costAmount - a.costAmount).slice(0, 8),
    [services],
  );
  const categorySpend = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of services) {
      const category = classifyService(row.service_name);
      totals.set(category, (totals.get(category) || 0) + row.costAmount);
    }
    return Array.from(totals, ([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
  }, [services]);
  const resourceSpend = useMemo(
    () =>
      resources
        .map((row) => ({
          name: row.resourceName,
          value: row.estimatedMonthlyCost || 0,
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 10),
    [resources],
  );
  const currentSpend = trends.reduce((sum, row) => sum + row.costAmount, 0);
  const potentialSavings = recommendations.reduce((sum, row) => sum + (row.estimatedSavings || 0), 0);

  return (
    <>
      <PageHeader title="Cost analytics" description="Azure Cost Management-style spend analytics and optimization views." />
      {loading ? (
        <div className="space-y-6">
          <ChartSkeleton message="Loading cost analytics..." />
          <div className="grid gap-6 xl:grid-cols-2">
            <ChartSkeleton message="Loading cost breakdown..." />
            <TableSkeleton rows={6} columns={4} />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Cost Trend</h2>
                <p className="text-sm text-muted-foreground">Daily, weekly, and monthly spend patterns.</p>
              </div>
              <div className="text-sm font-medium">{formatMoney(currentSpend, currency)} analyzed spend</div>
            </div>
            <div className="mt-5 h-96">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                  <XAxis dataKey="period" allowDuplicatedCategory={false} />
                  <YAxis />
                  <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                  <Legend />
                  <Line data={trends.map((row) => ({ period: row.date, value: row.costAmount }))} name="Daily spend" type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <Line data={weekly} name="Weekly spend" type="monotone" dataKey="value" stroke="#22c55e" strokeWidth={2} dot={false} />
                  <Line data={monthly.map((row) => ({ period: row.period, value: row.costAmount }))} name="Monthly spend" type="monotone" dataKey="value" stroke="#f59e0b" strokeWidth={2} dot />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <ChartCard title="Cost Breakdown" description="Spend grouped into FinOps categories.">
              <PieChart>
                <Pie data={categorySpend} dataKey="value" nameKey="name" innerRadius={70} outerRadius={115} paddingAngle={3}>
                  {categorySpend.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                <Legend />
              </PieChart>
            </ChartCard>

            <ChartCard title="Service Spend" description="Top spending Azure services.">
              <BarChart data={serviceSpend} layout="vertical" margin={{ left: 30 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis type="number" />
                <YAxis dataKey="service_name" type="category" width={150} />
                <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                <Bar dataKey="costAmount" fill="#3b82f6" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ChartCard>

            <ChartCard title="Top 10 Costing Resources" description="Ranked by estimated monthly resource cost.">
              <BarChart data={resourceSpend} layout="vertical" margin={{ left: 30 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis type="number" />
                <YAxis dataKey="name" type="category" width={150} />
                <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                <Bar dataKey="value" fill="#8b5cf6" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ChartCard>

            <ChartCard title="Savings Opportunities" description="Current spend compared with potential savings.">
              <BarChart data={[{ name: "Current Spend", value: currentSpend }, { name: "Potential Savings", value: potentialSavings }]}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                <Bar dataKey="value" fill="#22c55e" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ChartCard>
          </div>

          <Card className="p-5">
            <h2 className="font-semibold">Cost Heat Map</h2>
            <p className="mt-1 text-sm text-muted-foreground">Resource group contribution to total cost.</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[...groups].sort((a, b) => b.costAmount - a.costAmount).slice(0, 12).map((group) => {
                const intensity = Math.min(1, group.costAmount / Math.max(...groups.map((item) => item.costAmount), 1));
                return (
                  <div key={group.resource_group} className="rounded-xl border p-4" style={{ backgroundColor: `rgba(59, 130, 246, ${0.12 + intensity * 0.32})` }}>
                    <div className="truncate text-sm font-medium">{group.resource_group || "Unassigned"}</div>
                    <div className="mt-2 text-lg font-semibold">{formatMoney(group.costAmount, group.currency)}</div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function ChartCard({ title, description, children }: { title: string; description: string; children: React.ReactElement }) {
  return (
    <Card className="p-5">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      <div className="mt-5 h-80">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function toWeekly(rows: CostRow[]) {
  const buckets = new Map<string, number>();
  for (const row of rows) {
    const date = new Date(row.date || "");
    if (Number.isNaN(date.getTime())) continue;
    const week = new Date(date);
    week.setDate(date.getDate() - date.getDay());
    const key = week.toISOString().slice(0, 10);
    buckets.set(key, (buckets.get(key) || 0) + row.costAmount);
  }
  return Array.from(buckets, ([period, value]) => ({ period, value }));
}
