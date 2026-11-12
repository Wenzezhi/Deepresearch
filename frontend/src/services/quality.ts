import { api } from "./api";

export type QualitySeverity = "error" | "warn" | "info";

export interface QualityIssue {
  type: string;
  severity: QualitySeverity;
  message: string;
  url?: string;
  title?: string;
  section?: string;
  task_id?: number;
  line?: number;
  snippet?: string;
  quote?: string;
  count?: number;
}

export interface QualityMetrics {
  cited_links: number;
  cited_unique: number;
  retrieved_unique: number;
  verified: number;
  unverified: number;
  uncited: number;
  local_refs: number;
  sections: number;
  sections_without_source: number;
  coverage: number;
  source_usage: number;
  inline_citations: number;
}

export interface QualityCitation {
  url: string;
  title: string;
  form: string;
  section: string;
  line: number;
  snippet: string;
  quote: string;
  in_reference: boolean;
}

export interface QualitySource {
  index: number;
  url: string;
  title: string;
  domain: string;
  kind: "web" | "local" | string;
  task_ids: number[];
  cited: boolean;
  verified: boolean;
}

export interface QualityAudit {
  run_id: string;
  topic: string;
  report_available: boolean;
  metrics: QualityMetrics;
  score: number;
  grade: string;
  issues: QualityIssue[];
  issue_summary: Record<string, number>;
  sources: QualitySource[];
  citations: QualityCitation[];
  generated_at: string;
}

export interface QualityReportPayload {
  run_id: string;
  markdown: string;
  references_markdown: string;
  score: number;
  grade: string;
}

export function fetchQualityAudit(runId: string): Promise<QualityAudit> {
  return api<QualityAudit>(`/quality/audit/${encodeURIComponent(runId)}`);
}

export function fetchQualityReport(
  runId: string,
  style: "plain" | "gbt7714-lite" = "plain"
): Promise<QualityReportPayload> {
  return api<QualityReportPayload>("/quality/report", {
    method: "POST",
    body: JSON.stringify({ run_id: runId, style })
  });
}

export const ISSUE_LABELS: Record<string, string> = {
  unverified_url: "疑似编造/未核验链接",
  local_ref_missing: "本地文献已被删除",
  duplicate_citation: "重复引用",
  no_source_section: "章节无来源",
  missing_conclusion: "缺少结论段",
  missing_limitation: "缺少局限说明",
  empty_section: "空章节",
  heading_level_jump: "标题层级跳跃",
  report_too_short: "报告过短",
  few_sources: "来源过少",
  domain_concentration: "来源过于集中",
  task_without_sources: "任务没有来源",
  local_only_sources: "只有本地来源",
  missing_reference_section: "缺少参考文献段",
  empty_reference_section: "参考文献段为空",
  mixed_citation_style: "链接写法不统一",
  unlabelled_link: "链接缺少可读文字",
  no_inline_citations: "全文无行内引用",
  empty_report: "报告为空"
};

export const SEVERITY_LABELS: Record<QualitySeverity, string> = {
  error: "严重",
  warn: "警告",
  info: "提示"
};
