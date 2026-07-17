import { useState } from "react";
import { ClipboardList, Download, Trash2 } from "lucide-react";
import { Header } from "@/components/Header";
import { SingleReview } from "@/components/SingleReview";
import { BatchReview } from "@/components/BatchReview";
import { ResultCard } from "@/components/ResultCard";
import { StatsBar } from "@/components/StatsBar";
import { Button } from "@/components/ui/button";
import type { ReviewResult } from "@/types";

function App() {
  const [results, setResults] = useState<ReviewResult[]>([]);
  const [activeTab, setActiveTab] = useState<"single" | "batch">("single");

  const handleSingleResult = (result: ReviewResult) => {
    setResults((prev) => [result, ...prev]);
  };

  const handleBatchResults = (batchResults: ReviewResult[]) => {
    setResults((prev) => [...batchResults, ...prev]);
  };

  const handleClearResults = () => setResults([]);

  const handleExportCSV = () => {
    if (!results.length) return;
    const headers = ["offer_id", "flags", "concise_reason"];
    const rows = results.map((r) => [
      r.offer_id,
      r.flags.join("; "),
      `"${r.concise_reason.replace(/"/g, '""')}"`,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bl-review-results-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      {/* Background decoration */}
      <div className="bg-gradient-orb bg-gradient-orb-1" />
      <div className="bg-gradient-orb bg-gradient-orb-2" />

      <Header />

      <main className="relative z-10 mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {/* Hero section */}
        <div className="mb-8 text-center animate-slide-up">
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Buy Lead{" "}
            <span className="bg-gradient-to-r from-blue-600 via-cyan-500 to-teal-400 bg-clip-text text-transparent">
              Quality Reviewer
            </span>
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-muted-foreground leading-relaxed">
            Analyze IndiaMART buy leads for title, category, and ISQ consistency
            using AI. Submit individual leads or upload CSV files for batch processing.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[420px_1fr]">
          {/* Left — Input panel */}
          <div className="space-y-4">
            {/* Tab switcher */}
            <div className="flex rounded-xl border bg-muted/50 p-1">
              <button
                type="button"
                onClick={() => setActiveTab("single")}
                className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 ${
                  activeTab === "single"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Single
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("batch")}
                className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 ${
                  activeTab === "batch"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Batch CSV
              </button>
            </div>

            {activeTab === "single" ? (
              <SingleReview onResult={handleSingleResult} />
            ) : (
              <BatchReview onResults={handleBatchResults} />
            )}
          </div>

          {/* Right — Results panel */}
          <div className="space-y-4">
            {/* Results header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-5 w-5 text-muted-foreground" />
                <h3 className="text-lg font-semibold">
                  Results
                  {results.length > 0 && (
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({results.length})
                    </span>
                  )}
                </h3>
              </div>
              {results.length > 0 && (
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-1.5">
                    <Download className="h-3.5 w-3.5" />
                    Export
                  </Button>
                  <Button variant="ghost" size="sm" onClick={handleClearResults} className="gap-1.5 text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                    Clear
                  </Button>
                </div>
              )}
            </div>

            {/* Stats */}
            <StatsBar results={results} />

            {/* Result cards */}
            {results.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-muted-foreground/15 py-16 text-center animate-slide-up">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
                  <ClipboardList className="h-7 w-7 text-muted-foreground/50" />
                </div>
                <p className="text-sm font-medium text-muted-foreground">No results yet</p>
                <p className="mt-1 text-xs text-muted-foreground/60">
                  Submit a review to see results here
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {results.map((result, i) => (
                  <ResultCard key={`${result.offer_id}-${i}`} result={result} index={i} />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 mt-16 border-t py-6 text-center text-xs text-muted-foreground">
        <p>BL Reviewer Agent — Powered by FastAPI + Gemini AI</p>
      </footer>
    </div>
  );
}

export default App;
