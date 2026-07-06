export interface NavItem {
  title: string;
  href: string;
  icon: string; // Material Symbols icon name
  description?: string;
  badge?: string;
}

export const mainNav: NavItem[] = [
  { title: '信息助手', href: '/agent', icon: 'insights', description: '智能订阅管家' },
  { title: '工作台', href: '/workspace', icon: 'deployed_code', description: '工作流与自动化' },
  { title: '数据看板', href: '/dashboard', icon: 'monitoring', description: '数据总览与分析' },
  { title: '系统设置', href: '/settings/system', icon: 'settings', description: '监控 / 推送 / 模型 / 账号' },
];
