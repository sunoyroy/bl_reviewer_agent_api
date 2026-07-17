import { useState, useCallback, useRef } from "react";
import { Upload, FileSpreadsheet, Loader2, X, AlertCircle } from "lucide-react";
import Papa from "papaparse";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { reviewBatch } from "@/services/api";
import type { ReviewRequest, ReviewResult } from "@/types";

interface BatchReviewProps {
  onResults: (results: ReviewResult[]) => void;
}

export function BatchReview({ onResults }: BatchReviewProps) {
  const [file, setFile] = useState<File | null>(null);
  const [parsedRows, setParsedRows] = useState<ReviewRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setError("");
    setParsedRows([]);

    Papa.parse(f, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const rows: ReviewRequest[] = (results.data as Record<string, string>[]).map((row) => {
          const req: ReviewRequest = {};

          /* Map common CSV column names to our ReviewRequest fields */
          req.offer_id = row.offer_id || row.eto_ofr_display_id || row.Offer_ID || "";
          req.title = row.title || row.eto_ofr_title || row.Title || "";
          req.mcat = row.mcat || row.glcat_mcat_name || row.MCAT || row.Category || "";

          const attrRaw = row.attributes_combined || row.isq_filled || row.ISQ || "";
          if (attrRaw) {
            /* Try to parse "Key: Value; Key2: Value2" format */
            const pairs: Record<string, string> = {};
            for (const segment of attrRaw.split(";")) {
              const [k, ...rest] = segment.split(":");
              if (k && rest.length) {
                pairs[k.trim()] = rest.join(":").trim();
              }
            }
            if (Object.keys(pairs).length > 0) {
              req.isq_filled = pairs;
            }
          }

          return req;
        });

        setParsedRows(rows.filter((r) => r.title));
      },
      error: (err) => {
        setError(`Failed to parse CSV: ${err.message}`);
      },
    });
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith(".csv") || droppedFile.type === "text/csv")) {
      handleFile(droppedFile);
    } else {
      setError("Please drop a .csv file");
    }
  }, [handleFile]);

  const handleSubmitBatch = async () => {
    if (!parsedRows.length) return;

    setLoading(true);
    setError("");
    setProgress({ done: 0, total: parsedRows.length });

    /* Process in chunks of 10 to avoid overloading the server */
    const CHUNK_SIZE = 10;
    const allResults: ReviewResult[] = [];

    try {
      for (let i = 0; i < parsedRows.length; i += CHUNK_SIZE) {
        const chunk = parsedRows.slice(i, i + CHUNK_SIZE);
        const response = await reviewBatch(chunk);
        allResults.push(...response.results);
        setProgress({ done: allResults.length, total: parsedRows.length });
      }
      onResults(allResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch review failed");
    } finally {
      setLoading(false);
    }
  };

  const clearFile = () => {
    setFile(null);
    setParsedRows([]);
    setError("");
    setProgress({ done: 0, total: 0 });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <Card className="animate-slide-up stagger-1">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-violet-100 dark:bg-violet-950">
            <FileSpreadsheet className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
          </div>
          Batch Review
        </CardTitle>
        <CardDescription>
          Upload a CSV file to review multiple buy leads at once
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200
            ${dragActive
              ? "border-primary bg-primary/5 scale-[1.01]"
              : "border-muted-foreground/20 hover:border-primary/40 hover:bg-muted/50"
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <Upload className={`mx-auto mb-3 h-8 w-8 ${dragActive ? "text-primary" : "text-muted-foreground/50"}`} />
          <p className="text-sm font-medium">
            {file ? file.name : "Drop CSV here or click to browse"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Expected columns: title, mcat, offer_id, attributes_combined
          </p>
        </div>

        {/* File info */}
        {file && parsedRows.length > 0 && (
          <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3.5 py-2.5">
            <div className="flex items-center gap-2 text-sm">
              <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{parsedRows.length}</span>
              <span className="text-muted-foreground">leads found</span>
            </div>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={clearFile}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}

        {/* Progress */}
        {loading && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Processing...</span>
              <span>{progress.done} / {progress.total}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 transition-all duration-500"
                style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Submit */}
        <Button
          id="batch-review-btn"
          onClick={handleSubmitBatch}
          disabled={loading || !parsedRows.length}
          className="w-full"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing {progress.done}/{progress.total}...
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              Review {parsedRows.length || ""} Leads
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
