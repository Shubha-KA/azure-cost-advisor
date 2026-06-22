import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { CSSProperties } from "react";

export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <div className={cn("animate-pulse rounded-lg bg-muted", className)} style={style} />;
}

export function MetricSkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, index) => (
        <Card key={index} className="min-h-32 p-5">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="mt-4 h-8 w-36" />
          <Skeleton className="mt-3 h-3 w-44" />
        </Card>
      ))}
    </div>
  );
}

export function ChartSkeleton({ message }: { message: string }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-3 h-3 w-56" />
        </div>
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
      <div className="mt-6 h-64 overflow-hidden rounded-xl border bg-background/40 p-4">
        <div className="flex h-full items-end gap-2">
          {Array.from({ length: 18 }).map((_, index) => (
            <Skeleton
              key={index}
              className="min-w-0 flex-1 rounded-t-md"
              style={{ height: `${22 + ((index * 13) % 68)}%` }}
            />
          ))}
        </div>
      </div>
      <p className="mt-4 text-center text-sm text-muted-foreground">{message}</p>
    </Card>
  );
}

export function TableSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-8 w-32" />
      </div>
      <div className="overflow-hidden rounded-xl border bg-background/40">
        <div className="grid gap-4 border-b bg-muted/20 p-4" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: columns }).map((_, column) => (
            <Skeleton key={column} className="h-3 w-3/4" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, row) => (
          <div key={row} className="grid gap-4 border-b p-4 last:border-b-0" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
            {Array.from({ length: columns }).map((__, column) => (
              <Skeleton key={column} className="h-4 w-full max-w-40" />
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}

export function StatusPill({ label, tone }: { label: string; tone?: string }) {
  return (
    <span className={cn("inline-flex rounded-full px-2.5 py-1 text-xs font-medium", tone || "bg-muted text-muted-foreground")}>
      {label}
    </span>
  );
}
