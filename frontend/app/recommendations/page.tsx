"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { DataTable } from "@/components/data-table";

type Recommendation = { title: string; category: string; estimatedSavings: number; currency: string; sourceSystem: string; status: string };

export default function Recommendations() {
  const { scope } = useScope();
  const [rows, setRows] = useState<Recommendation[]>([]);
  useEffect(() => {
    if (scope.subscriptionId) api<Recommendation[]>("/api/recommendations", scope).then(setRows);
  }, [scope]);
  return (
    <>
      <PageHeader title="Recommendations" description="Optimization, Advisor findings, and savings opportunities." />
      <DataTable data={rows} columns={[
        { accessorKey: "title", header: "Finding" }, { accessorKey: "category", header: "Category" },
        { accessorKey: "estimatedSavings", header: "Savings" }, { accessorKey: "currency", header: "Currency" },
        { accessorKey: "sourceSystem", header: "Source" }, { accessorKey: "status", header: "Status" },
      ]} />
    </>
  );
}
