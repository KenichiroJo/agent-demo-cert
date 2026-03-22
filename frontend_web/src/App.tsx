import { useState } from 'react';
import { SidebarProvider } from '@/components/ui/sidebar';
import { RetailDashboardTab } from '@/retail/RetailDashboardTab';
import RetailChatAssistant from '@/retail/components/RetailChatAssistant';

type ActiveTab = 'dashboard' | 'chat';

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');

  return (
    <SidebarProvider>
      <div className="flex h-svh w-full flex-col">
        {/* Header with tab navigation */}
        <header className="flex items-center justify-between border-b border-border bg-background px-6 py-3">
          <nav className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab('dashboard')}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-muted text-accent'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-accent-foreground'
              }`}
            >
              売上予測ダッシュボード
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('chat')}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold transition-all ${
                activeTab === 'chat'
                  ? 'bg-muted text-accent'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-accent-foreground'
              }`}
            >
              AIアシスタント
            </button>
          </nav>
        </header>

        {/* Main content area — both tabs always mounted, hidden via display:none */}
        <div className="flex flex-1 overflow-hidden w-full">
          <div className="w-full h-full" style={{ display: activeTab === 'dashboard' ? 'contents' : 'none' }}>
            <RetailDashboardTab />
          </div>
          <div className="w-full h-full" style={{ display: activeTab === 'chat' ? 'contents' : 'none' }}>
            <RetailChatAssistant />
          </div>
        </div>
      </div>
    </SidebarProvider>
  );
}
