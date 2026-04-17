import Link from "next/link";
import { ArrowRight, Bot, ClipboardCheck, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const highlights = [
  {
    title: "结构化评测",
    description: "专家主要做选择和确认，避免长篇论述，提升评测一致性。",
    icon: ClipboardCheck
  },
  {
    title: "LLM 辅助改写",
    description: "在任务内直接发起事实核查、风险分析和标准答案候选生成。",
    icon: Bot
  },
  {
    title: "审核制专家体系",
    description: "专家先注册后审核，按应用领域分发，保证评测质量和稳定性。",
    icon: ShieldCheck
  }
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background bg-mesh px-4 py-5 text-foreground lg:px-6">
      <div className="mx-auto max-w-[1480px] rounded-[36px] border border-white/70 bg-white/82 p-6 shadow-soft backdrop-blur lg:p-10">
        <header className="grid gap-8 lg:grid-cols-[1.3fr_0.9fr] lg:items-end">
          <div className="space-y-6">
            <span className="inline-flex rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">
              QA 评测平台 MVP
            </span>
            <div className="space-y-4">
              <h1 className="max-w-4xl font-serif text-4xl leading-tight lg:text-6xl">
                面向专家与 LLM 协作的
                <br />
                QA 对质量评测工作台
              </h1>
              <p className="max-w-2xl text-base leading-8 text-muted-foreground lg:text-lg">
                用轻量化流程把 JSON QA 数据导入、分发、评测、改写和聚合串成一个闭环。
                平台重点不在自由标注，而在稳定地产出可训练的标准答案与质量标签。
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button asChild>
                <Link href="/expert">
                  进入专家端
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="secondary">
                <Link href="/admin">进入管理端</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/login">登录</Link>
              </Button>
            </div>
          </div>
          <Card className="overflow-hidden bg-stone-50">
            <CardHeader>
              <CardTitle className="font-serif text-2xl">工作流概览</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                "管理员导入 JSON 数据并审核专家注册",
                "系统按应用领域给专家分发至少 2 份评测任务",
                "专家在任务内调用 LLM 做核查与候选答案生成",
                "系统聚合结果，管理员确认最终标准答案"
              ].map((step, index) => (
                <div
                  key={step}
                  className="flex items-start gap-4 rounded-3xl border border-border bg-white p-4"
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                    {index + 1}
                  </div>
                  <p className="text-sm leading-7 text-muted-foreground">{step}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </header>

        <section className="mt-8 grid gap-4 lg:grid-cols-3">
          {highlights.map(({ title, description, icon: Icon }) => (
            <Card key={title} className="bg-white/90">
              <CardHeader className="space-y-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
                  <Icon className="h-5 w-5" />
                </div>
                <CardTitle>{title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-7 text-muted-foreground">{description}</p>
              </CardContent>
            </Card>
          ))}
        </section>
      </div>
    </main>
  );
}
