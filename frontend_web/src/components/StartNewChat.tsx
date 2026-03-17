import { Button } from '@/components/ui/button';

export function StartNewChat({ createChat }: { createChat: () => void }) {
  return (
    <section className="flex min-h-full flex-1 items-center justify-center px-6 py-12 text-center">
      <div className="flex w-full max-w-md flex-col items-center gap-6 rounded-lg px-8 py-10 shadow-xs">
        <div className="space-y-3">
          <p className="heading-02 capitalize">チャットが選択されていません</p>
          <p className="body-secondary">
            サイドバーから既存の会話を選択するか、新しいチャットを開始してください。
          </p>
        </div>
        <Button size="lg" onClick={createChat}>
          新しいチャットを開始
        </Button>
      </div>
    </section>
  );
}
