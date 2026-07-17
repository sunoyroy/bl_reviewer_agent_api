import { useState, useEffect } from "react";
import { Moon, Sun, Zap, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { healthCheck } from "@/services/api";

export function Header() {
  const [dark, setDark] = useState(() => {
    if (typeof window !== "undefined") {
      return document.documentElement.classList.contains("dark");
    }
    return false;
  });
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    healthCheck()
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, []);

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500 shadow-lg shadow-blue-500/25">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight">
              BL Reviewer <span className="bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Agent</span>
            </h1>
            <p className="text-[11px] text-muted-foreground -mt-0.5">AI-powered Quality Analysis</p>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-3">
          {/* API Status */}
          <div className="flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium">
            <Activity className={`h-3 w-3 ${
              apiStatus === "online" ? "text-emerald-500" :
              apiStatus === "offline" ? "text-red-500" : "text-amber-500 animate-pulse"
            }`} />
            <span className="text-muted-foreground">
              {apiStatus === "online" ? "API Connected" :
               apiStatus === "offline" ? "API Offline" : "Checking..."}
            </span>
          </div>

          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDark(!dark)}
            aria-label="Toggle theme"
            className="rounded-full"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
