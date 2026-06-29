import { Link, useLocation } from "react-router";
import { motion } from "framer-motion";
import { 
  LayoutDashboard, 
  BarChart3, 
  Timer, 
  Settings, 
  GitBranch as Github,
  ChevronLeft,
  Sparkles,
  Users2
} from "lucide-react";
import { cn } from "@/utils";
import { useAppStore } from "@/store";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { name: "Dashboard", path: "/", icon: LayoutDashboard },
  { name: "Pipeline Demo", path: "/pipeline", icon: Sparkles },
  { name: "Candidates", path: "/candidates", icon: Users2 },
  { name: "Analytics", path: "/analytics", icon: BarChart3 },
  { name: "Benchmarks", path: "/benchmarks", icon: Timer },
  { name: "Settings", path: "/settings", icon: Settings },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useAppStore();
  const location = useLocation();

  return (
    <motion.aside
      initial={false}
      animate={{ 
        width: sidebarOpen ? 256 : 80,
      }}
      transition={{ type: "spring", bounce: 0, duration: 0.3 }}
      className="h-screen bg-card border-r border-border relative flex flex-col z-20 flex-shrink-0"
    >
      <div className="p-4 flex items-center justify-between h-16 border-b border-border">
        <div className="flex items-center gap-3 overflow-hidden whitespace-nowrap">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center flex-shrink-0">
            <span className="text-primary-foreground font-bold text-sm">R</span>
          </div>
          {sidebarOpen && (
            <motion.span 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="font-bold text-lg"
            >
              Redrob AI
            </motion.span>
          )}
        </div>
      </div>

      <Button
        variant="outline"
        size="icon"
        className="absolute -right-4 top-5 w-8 h-8 rounded-full shadow-sm z-50 bg-background"
        onClick={toggleSidebar}
      >
        <motion.div animate={{ rotate: sidebarOpen ? 0 : 180 }}>
          <ChevronLeft className="h-4 w-4" />
        </motion.div>
      </Button>

      <div className="flex-1 overflow-y-auto py-6 px-3 flex flex-col gap-2">
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link key={item.path} to={item.path}>
              <div
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md transition-colors whitespace-nowrap overflow-hidden",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {sidebarOpen && (
                  <span className="font-medium text-sm">{item.name}</span>
                )}
              </div>
            </Link>
          );
        })}
      </div>

      <div className="p-4 border-t border-border">
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 px-3 py-2 text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-secondary whitespace-nowrap overflow-hidden"
        >
          <Github className="h-5 w-5 flex-shrink-0" />
          {sidebarOpen && <span className="font-medium text-sm">GitHub</span>}
        </a>
      </div>
    </motion.aside>
  );
}
