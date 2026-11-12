/**
 * 原文质检标记图层。
 *
 * 只对已经渲染好的报告 DOM 做"装饰"：加高亮类、插角标、滚动定位。
 * 不修改 MarkdownDocument 组件、不改报告内容、不拦截任何事件；
 * 关闭开关时移除全部标记，DOM 与原始渲染完全一致。
 */
import type { QualityIssue } from "../services/quality";

const FLAG_CLASS = "rqg-flagged";
const FLASH_CLASS = "rqg-flash";
const BADGE_ATTR = "data-rqg-badge";

interface MarkerRecord {
  el: HTMLElement;
  className: string;
  badge?: HTMLElement;
}

export interface MarkerTarget {
  section?: string;
  snippet?: string;
}

function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function resolveRoot(button: HTMLElement | null): HTMLElement | null {
  const card = button?.closest(".document-card");
  if (card) return card.querySelector<HTMLElement>(".markdown-body");
  return null;
}

function headingCandidates(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6"));
}

function textCandidates(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("p,li,blockquote,td"));
}

export class QualityMarkerLayer {
  private root: HTMLElement | null;
  private markers: MarkerRecord[] = [];
  private cleanups: Array<() => void> = [];

  constructor(button: HTMLElement | null) {
    this.root = resolveRoot(button);
  }

  get available(): boolean {
    return this.root !== null;
  }

  /** 重新解析容器（报告重新渲染后 DOM 会被替换）。 */
  refresh(button: HTMLElement | null): void {
    this.clear();
    this.root = resolveRoot(button);
  }

  apply(issues: QualityIssue[]): number {
    this.clear();
    if (!this.root || !issues.length) return 0;
    const headings = headingCandidates(this.root);
    const used = new Set<HTMLElement>();

    for (const issue of issues) {
      const target = this.findTarget(issue, headings);
      if (!target || used.has(target)) continue;
      used.add(target);
      target.classList.add(FLAG_CLASS);
      const badge = document.createElement("span");
      badge.setAttribute(BADGE_ATTR, issue.severity);
      badge.className = "rqg-inline-badge";
      badge.textContent =
        issue.severity === "error" ? "✕" : issue.severity === "warn" ? "!" : "i";
      badge.title = issue.message;
      target.appendChild(badge);
      this.markers.push({ el: target, className: FLAG_CLASS, badge });
    }
    return this.markers.length;
  }

  private findTarget(issue: MarkerTarget, headings: HTMLElement[]): HTMLElement | null {
    if (!this.root) return null;
    if (issue.snippet) {
      const wanted = normalize(issue.snippet).slice(0, 50);
      if (wanted.length >= 6) {
        const paragraph = textCandidates(this.root).find((item) =>
          normalize(item.textContent || "").includes(wanted)
        );
        if (paragraph) return paragraph;
      }
    }
    if (issue.section) {
      const wanted = normalize(issue.section);
      const heading = headings.find((item) => normalize(item.textContent || "") === wanted)
        || headings.find((item) => normalize(item.textContent || "").includes(wanted));
      if (heading) return heading;
    }
    return null;
  }

  locate(target: MarkerTarget): boolean {
    this.clear();
    if (!this.root) return false;
    const headings = headingCandidates(this.root);
    const element = this.findTarget(target, headings);
    if (!element) return false;
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    element.classList.add(FLAG_CLASS, FLASH_CLASS);
    const timer = window.setTimeout(() => {
      element.classList.remove(FLASH_CLASS);
    }, 2400);
    this.cleanups.push(() => window.clearTimeout(timer));
    this.markers.push({ el: element, className: FLAG_CLASS });
    return true;
  }

  clear(): void {
    for (const marker of this.markers) {
      marker.el.classList.remove(marker.className, FLASH_CLASS);
      marker.badge?.remove();
    }
    this.markers = [];
    for (const cleanup of this.cleanups) cleanup();
    this.cleanups = [];
    if (this.root) {
      this.root
        .querySelectorAll<HTMLElement>("[data-rqg-badge]")
        .forEach((node) => node.remove());
      this.root
        .querySelectorAll<HTMLElement>(`.${FLAG_CLASS}`)
        .forEach((node) => node.classList.remove(FLAG_CLASS, FLASH_CLASS));
    }
  }
}

export { FLAG_CLASS, FLASH_CLASS };
