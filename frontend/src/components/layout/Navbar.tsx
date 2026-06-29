import { Moon, Sun, Bell, Search } from "lucide-react";
import { useTheme } from "@/components/common/ThemeProvider";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

export function Navbar() {
  const { theme, setTheme } = useTheme();

  return (
    <header className="h-16 border-b border-border bg-card px-6 flex items-center justify-between sticky top-0 z-10 flex-shrink-0">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Overview</h2>
        <Badge variant="secondary" className="font-normal text-xs px-2 py-0.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 mr-1.5 inline-block" />
          System Online
        </Badge>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative hidden md:flex items-center">
          <Search className="absolute left-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search candidates..."
            className="h-9 w-64 rounded-md border border-input bg-background px-3 pl-9 text-sm text-foreground shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>

        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          <span className="absolute top-2 right-2.5 h-2 w-2 rounded-full bg-destructive" />
        </Button>

        <div className="h-6 w-px bg-border mx-1" />

        <Avatar className="h-8 w-8 cursor-pointer ring-1 ring-border">
          <AvatarImage src="https://github.com/shadcn.png" alt="@shadcn" />
          <AvatarFallback>RR</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
