import { CheckCircle2, AlertTriangle, Flag, ChevronDown, ChevronUp, Hash } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ReviewResult } from "@/types";
import { useState } from "react";

interface ResultCardProps {
  result: ReviewResult;
  index: number;
}

const FLAG_COLORS: Record<string, "destructive" | "warning" | "default"> = {
  /* Known flags from the agent — map to semantic badge variants */
  TITLE_MISMATCH: "destructive",
  CATEGORY_MISMATCH: "destructive",
  ISQ_INCONSISTENT: "warning",
  ISQ_MISSING: "warning",
  VAGUE_TITLE: "warning",
  SPAM: "destructive",
  DUPLICATE: "warning",
};

function getFlagVariant(flag: string): "destructive" | "warning" | "default" {
  return FLAG_COLORS[flag.toUpperCase()] || FLAG_COLORS[flag] || "default";
}

export function ResultCard({ result, index }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false);
  const hasFlagged = result.flags.length > 0;
  const delayClass = `stagger-${Math.min((index % 5) + 1, 5)}`;

  return (
    <Card
      className={`animate-slide-up ${delayClass} overflow-hidden transition-all duration-300 ${
        hasFlagged
          ? "border-amber-300/50 dark:border-amber-700/40"
          : "border-emerald-300/50 dark:border-emerald-700/40"
      }`}
    >
      <CardContent className="p-0">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
        >
          {/* Status icon */}
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
            hasFlagged
              ? "bg-amber-100 dark:bg-amber-950"
              : "bg-emerald-100 dark:bg-emerald-950"
          }`}>
            {hasFlagged ? (
              <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {result.offer_id && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground font-mono">
                  <Hash className="h-3 w-3" />
                  {result.offer_id}
                </span>
              )}
              {hasFlagged ? (
                <Badge variant="warning" className="text-[10px]">
                  {result.flags.length} {result.flags.length === 1 ? "flag" : "flags"}
                </Badge>
              ) : (
                <Badge variant="success" className="text-[10px]">Clean</Badge>
              )}
            </div>
            <p className="mt-0.5 text-sm truncate text-foreground/80">
              {result.concise_reason || "No issues detected"}
            </p>
          </div>

          {/* Expand */}
          <div className="shrink-0 text-muted-foreground">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
        </button>

        {/* Expanded details */}
        {expanded && (
          <div className="border-t bg-muted/20 px-4 py-3 space-y-3 animate-slide-up">
            {/* Flags */}
            {hasFlagged && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1">
                  <Flag className="h-3 w-3" /> Flags
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.flags.map((flag) => (
                    <Badge key={flag} variant={getFlagVariant(flag)}>
                      {flag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Reason */}
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Reason</p>
              <p className="text-sm leading-relaxed">{result.concise_reason || "—"}</p>
            </div>

            {/* Raw JSON */}
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Raw Response</p>
              <pre className="overflow-x-auto rounded-lg bg-background border p-3 text-xs leading-relaxed">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
