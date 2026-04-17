import { AuthGuard } from "@/components/auth-guard";
import { AppShell, type NavItem } from "@/components/app-shell";

const navItems: NavItem[] = [
  { href: "/admin", label: "仪表盘", hint: "查看整体进度和关键指标" },
  { href: "/admin/experts", label: "专家审核", hint: "审核注册、停用或查看详情" },
  { href: "/admin/applications", label: "应用管理", hint: "维护领域和启用状态" },
  { href: "/admin/imports", label: "数据导入", hint: "上传 JSON 并跟踪批次" },
  { href: "/admin/qas", label: "QA 数据", hint: "查看问题、答案与聚合结果" },
  { href: "/admin/tasks", label: "任务分发", hint: "管理初评与争议复核任务" },
  { href: "/admin/analytics", label: "统计分析", hint: "查看通过率、争议率和覆盖情况" },
  { href: "/admin/exports", label: "结果导出", hint: "导出训练数据与评测明细" }
];

export default function AdminLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <AuthGuard role="admin">
      <AppShell
        title="管理控制台"
        subtitle="围绕导入、审核、分发、聚合和最终标准答案确认形成完整运营闭环。"
        navItems={navItems}
        roleLabel="Admin Console"
      >
        {children}
      </AppShell>
    </AuthGuard>
  );
}
