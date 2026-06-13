'use client';

/**
 * LoginBrief —— 登录简报（gold 主题卡片）。
 */
import { Button } from '@/components/ui/button';
import { DashboardCards } from './brief/DashboardCards';
import { HotTopics } from './brief/HotTopics';

interface Props {
  onAction?: (msg: string) => void;
}

export function LoginBrief({ onAction }: Props) {
  return (
    <div className="space-y-2">
      <DashboardCards />
      <HotTopics onAction={onAction} />
      {onAction && (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => onAction('看看今天有哪些话题')}
          >
            查看话题
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => onAction('触发一次扫描')}
          >
            触发扫描
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => onAction('今天有什么需要关注的')}
          >
            今日全部
          </Button>
        </div>
      )}
    </div>
  );
}
