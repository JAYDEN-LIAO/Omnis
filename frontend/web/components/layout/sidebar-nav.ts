export interface NavItem {
  title: string;
  href: string;
  icon: string; // Material Symbols icon name
  description?: string;
  badge?: string;
}

export const mainNav: NavItem[] = [
  { title: '信息助手', href: '/agent', icon: 'insights', description: '智能订阅管家' },
  { title: '总览仪表盘', href: '/dashboard', icon: 'radar', description: '今日舆情速览' },
  { title: '入库信息', href: '/list', icon: 'auto_stories', description: '话题与帖子' },
  { title: '系统设置', href: '/settings/system', icon: 'sensors', description: '监控 / 推送 / 模型 / 账号' },
];
