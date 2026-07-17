import { useState, type FormEvent } from "react";
import { Send, Plus, Trash2, Loader2 } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { reviewSingle } from "@/services/api";
import type { ReviewResult, ReviewStatus } from "@/types";

interface ISQPair {
  key: string;
  value: string;
}

interface SingleReviewProps {
  onResult: (result: ReviewResult) => void;
}

export function SingleReview({ onResult }: SingleReviewProps) {
  const [offerId, setOfferId] = useState("");
  const [title, setTitle] = useState("");
  const [mcat, setMcat] = useState("");
  const [isqPairs, setIsqPairs] = useState<ISQPair[]>([{ key: "", value: "" }]);
  const [status, setStatus] = useState<ReviewStatus>("idle");
  const [error, setError] = useState("");

  const addPair = () => setIsqPairs([...isqPairs, { key: "", value: "" }]);

  const removePair = (index: number) => {
    setIsqPairs(isqPairs.filter((_, i) => i !== index));
  };

  const updatePair = (index: number, field: "key" | "value", val: string) => {
    const updated = [...isqPairs];
    updated[index] = { ...updated[index], [field]: val };
    setIsqPairs(updated);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setStatus("loading");
    setError("");

    const isqFilled: Record<string, string> = {};
    for (const pair of isqPairs) {
      if (pair.key.trim() && pair.value.trim()) {
        isqFilled[pair.key.trim()] = pair.value.trim();
      }
    }

    try {
      const apiResult = await reviewSingle({
        offer_id: offerId.trim() || undefined,
        title: title.trim(),
        mcat: mcat.trim() || undefined,
        isq_filled: Object.keys(isqFilled).length > 0 ? isqFilled : undefined,
      });
      setStatus("success");
      // Attach offer_id to result since API doesn't return it
      onResult({
        ...apiResult,
        offer_id: offerId.trim() || "Unknown",
      });
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Review failed");
    }
  };

  const handleClear = () => {
    setOfferId("");
    setTitle("");
    setMcat("");
    setIsqPairs([{ key: "", value: "" }]);
    setStatus("idle");
    setError("");
  };

  const inputClass =
    "w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary/50 transition-all duration-200";

  return (
    <Card className="animate-slide-up">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-100 dark:bg-blue-950">
            <Send className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
          </div>
          Single Review
        </CardTitle>
        <CardDescription>
          Submit a buy lead for AI-powered quality analysis
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Offer ID */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Offer ID <span className="text-muted-foreground/50">(optional)</span>
            </label>
            <input
              id="offer-id-input"
              type="text"
              placeholder="e.g. 146420001285"
              value={offerId}
              onChange={(e) => setOfferId(e.target.value)}
              className={inputClass}
            />
          </div>

          {/* Title */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Title <span className="text-destructive">*</span>
            </label>
            <input
              id="title-input"
              type="text"
              required
              placeholder="e.g. BOPP Synthetic Non Tearable Sheets"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={inputClass}
            />
          </div>

          {/* MCAT */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              MCAT (Category)
            </label>
            <input
              id="mcat-input"
              type="text"
              placeholder="e.g. Non Tearable Paper"
              value={mcat}
              onChange={(e) => setMcat(e.target.value)}
              className={inputClass}
            />
          </div>

          {/* ISQ Attributes */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs font-medium text-muted-foreground">ISQ Attributes</label>
              <Button type="button" variant="ghost" size="sm" onClick={addPair} className="h-7 text-xs gap-1">
                <Plus className="h-3 w-3" /> Add
              </Button>
            </div>
            <div className="space-y-2">
              {isqPairs.map((pair, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input
                    type="text"
                    placeholder="Attribute name"
                    value={pair.key}
                    onChange={(e) => updatePair(i, "key", e.target.value)}
                    className={`${inputClass} flex-1`}
                  />
                  <input
                    type="text"
                    placeholder="Value"
                    value={pair.value}
                    onChange={(e) => updatePair(i, "value", e.target.value)}
                    className={`${inputClass} flex-1`}
                  />
                  {isqPairs.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => removePair(i)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <Button
              id="submit-review-btn"
              type="submit"
              disabled={status === "loading" || !title.trim()}
              className="flex-1"
            >
              {status === "loading" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Review
                </>
              )}
            </Button>
            <Button type="button" variant="outline" onClick={handleClear}>
              Clear
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
