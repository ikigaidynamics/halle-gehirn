import { useEffect } from "preact/hooks";
import { Topbar } from "./components/Topbar";
import { Rail } from "./components/Rail";
import { Conversation } from "./components/Conversation";
import { Inspector } from "./components/Inspector";
import { Footer } from "./components/Footer";
import { refreshHealth } from "./state/store";

export function App() {
  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div class="h-screen flex flex-col bg-surface">
      <Topbar />
      <div class="flex-1 flex min-h-0">
        <Rail />
        <Conversation />
        <Inspector />
      </div>
      <Footer />
    </div>
  );
}
