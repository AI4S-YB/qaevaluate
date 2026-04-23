import { AuthGuard } from "@/components/auth-guard";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ExpertPreviewBanner } from "@/components/expert-preview-banner";

const navItems: NavItem[] = [
  { href: "/expert", label: "工作台", hint: "任务概览与快捷入口" },
  { href: "/expert/tasks", label: "任务列表", hint: "查看待评与争议复核任务" },
  { href: "/expert/imports", label: "我的上传", hint: "上传 QA 批次，推进自评和互评" },
  { href: "/expert/history", label: "我的历史", hint: "查看已提交的评测记录" },
  { href: "/expert/model-trial", label: "模型试用", hint: "选模型、带题对话，检查训练或微调后的效果" },
  { href: "/expert/profile", label: "我的资料", hint: "维护领域场景和个人简介" }
];

export default function ExpertLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <AuthGuard role="expert" allowAdmin>
      <AppShell
        title="专家评测端"
        subtitle="围绕单个任务完成结构化打分、LLM 辅助分析和候选标准答案确认。"
        navItems={navItems}
        roleLabel="Expert Workspace"
      >
        <ExpertPreviewBanner />
        {children}
      </AppShell>
    </AuthGuard>
  );
}
