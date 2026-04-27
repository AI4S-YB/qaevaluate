import { AuthGuard } from "@/components/auth-guard";
import { AppShell, type NavItem } from "@/components/app-shell";

const navItems: NavItem[] = [
  { href: "/admin", label: "仪表盘", hint: "查看整体进度和关键指标" },
  { href: "/admin/system-status", label: "系统状态", hint: "查看模型、队列和备份运行情况" },
  { href: "/admin/experts", label: "专家审核", hint: "审核注册、停用或查看详情" },
  { href: "/admin/applications", label: "项目管理", hint: "维护项目启用状态和专家覆盖" },
  { href: "/admin/taxonomy", label: "分类配置", hint: "维护 QA 类型与领域场景" },
  { href: "/admin/llm-configs", label: "评测模型", hint: "维护 QA 评测链路使用的模型配置" },
  { href: "/admin/trial-llm-configs", label: "试用模型", hint: "维护专家端模型试用使用的独立对话配置" },
  { href: "/admin/models/changelog", label: "模型变更", hint: "查看试用模型的新增与更新历史" },
  { href: "/admin/imports", label: "数据导入", hint: "上传 JSON 并跟踪批次" },
  { href: "/admin/qas", label: "QA 数据", hint: "查看问题、答案与聚合结果" },
  { href: "/admin/tasks", label: "任务分发", hint: "管理初评与争议复核任务" },
  { href: "/admin/analytics", label: "统计分析", hint: "查看通过率、争议率和覆盖情况" },
  { href: "/admin/exports", label: "结果导出", hint: "导出训练数据与评测明细" },
  { href: "/admin/news", label: "新闻管理", hint: "发布系统公告与新闻内容" },
  { href: "/admin/feedbacks", label: "用户反馈", hint: "查看专家提交的使用反馈与建议" }
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
