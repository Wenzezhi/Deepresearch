/**
 * 原文质检标记图层。
 *
 * 只对已经渲染好的报告 DOM 做"装饰"：给具体链接、句子、段落加高亮并插入角标，
 * 关闭开关时全部移除、DOM 复原。不修改 MarkdownDocument 组件，也不拦截事件。
 */
import type { QualityIssue } from "../services/quality";

const FLAG_CLASS = "rqg-flagged";
const FOCUS_CLASS = "rqg-focus";
const SENTENCE_CLASS = "rqg-sentence";
const FLASH_CLASS = "rqg-flash";
const BADGE_ATTR = "data-rqg-badge";

export interface MarkerTarget {
  url?: string;
  quote?: string;
  snippet?: string;
  section?: string;
}

interface MarkerRecord {
  el: HTMLElement;
  className: string;
  badge?: HTMLElement;
}

function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function urlKey(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    const path = parsed.pathname.replace(/\/$/, "");
    return `${host}${path}`.toLowerCase();
  } catch {
    return url.trim().toLowerCase();
  }
}

function resolveRoot(button: HTMLElement | null): HTMLElement | null {
  const card = button?.closest(".document-card");
  if (card) return card.querySelector<HTMLElement>(".markdown-body");
  return null;
}

function headingCandidates(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6"));
}

const BLOCK_SELECTOR = "p,li,blockquote,td,h1,h2,h3,h4,h5,h6";

function blockOf(node: Node | null, root: HTMLElement): HTMLElement | null {
  let current: Node | null = node;
  while (current && current !== root) {
    if (current instanceof HTMLElement && current.matches(BLOCK_SELECTOR)) return current;
    current = current.parentNode;
  }
  return null;
}

export class QualityMarkerLayer {
  private root: HTMLElement | null;
  private markers: MarkerRecord[] = [];
  private wrappers: HTMLElement[] = [];
  private cleanups: Array<() => void> = [];

  constructor(button: HTMLElement | null) {
    this.root = resolveRoot(button);
  }

  get available(): boolean {
    return this.root !== null;
  }

  refresh(button: HTMLElement | null): void {
    this.clear();
    this.root = resolveRoot(button);
  }

  /** 在报告中标出问题位置：链接级优先，其次句子/段落，最后章节标题。 */
  apply(issues: QualityIssue[]): number {
    this.clear();
    if (!this.root) return 0;
    const used = new Set<HTMLElement>();

    for (const issue of issues) {
      const located = this.resolve(issue);
      if (!located || used.has(located.block)) continue;
      used.add(located.block);
      located.block.classList.add(FLAG_CLASS);
      const badge = document.createElement("span");
      badge.setAttribute(BADGE_ATTR, issue.severity);
      badge.className = "rqg-inline-badge";
      badge.textContent =
        issue.severity === "error" ? "✕" : issue.severity === "warn" ? "!" : "i";
      badge.title = issue.message;
      located.block.appendChild(badge);
      this.markers.push({ el: located.block, className: FLAG_CLASS, badge });
    }
    return this.markers.length;
  }

  /** 精确定位：优先跳到具体链接，其次跳到具体句子。 */
  locate(target: MarkerTarget): boolean {
    this.clear();
    if (!this.root) return false;
    const located = this.resolve(target);
    if (!located) return false;

    if (located.anchor) {
      located.anchor.classList.add(FOCUS_CLASS, FLASH_CLASS);
      located.anchor.scrollIntoView({ behavior: "smooth", block: "center" });
      const timer = window.setTimeout(() => {
        located.anchor?.classList.remove(FLASH_CLASS);
      }, 2400);
      this.cleanups.push(() => window.clearTimeout(timer));
      this.markers.push({ el: located.anchor, className: FOCUS_CLASS });
      return true;
    }

    located.block.classList.add(FLAG_CLASS, FLASH_CLASS);
    located.block.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => {
      located.block.classList.remove(FLASH_CLASS);
    }, 2400);
    this.cleanups.push(() => window.clearTimeout(timer));
    this.markers.push({ el: located.block, className: FLAG_CLASS });
    return true;
  }

  private resolve(target: MarkerTarget): { block: HTMLElement; anchor?: HTMLAnchorElement } | null {
    if (!this.root) return null;

    if (target.url) {
      const anchor = this.findAnchor(target.url);
      if (anchor) {
        const block = blockOf(anchor, this.root) || anchor;
        return { block, anchor };
      }
    }

    const text = normalize(target.quote || target.snippet || "");
    if (text.length >= 6) {
      const wrapper = this.wrapText(text.slice(0, 60));
      if (wrapper) {
        this.wrappers.push(wrapper);
        const block = blockOf(wrapper, this.root);
        if (block) return { block };
        return { block: wrapper };
      }
    }

    if (target.section) {
      const wanted = normalize(target.section);
      const headings = headingCandidates(this.root);
      const heading =
        headings.find((item) => normalize(item.textContent || "") === wanted) ||
        headings.find((item) => normalize(item.textContent || "").includes(wanted));
      if (heading) return { block: heading };
    }
    return null;
  }

  private findAnchor(url: string): HTMLAnchorElement | null {
    if (!this.root) return null;
    const wanted = urlKey(url);
    const anchors = Array.from(this.root.querySelectorAll<HTMLAnchorElement>("a[href]"));
    return (
      anchors.find((anchor) => urlKey(anchor.getAttribute("href") || "") === wanted) || null
    );
  }

  /** 在文本节点中把目标句子包成 span，实现句子级高亮。 */
  private wrapText(text: string): HTMLElement | null {
    if (!this.root || !text) return null;
    const walker = document.createTreeWalker(this.root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode() as Text | null;
    while (node) {
      const content = normalize(node.data);
      if (content.includes(text)) {
        const raw = node.data;
        const index = raw.indexOf(text);
        if (index < 0) {
          // 空白差异导致定位不到，退化为文本节点父元素
          return blockOf(node, this.root);
        }
        const range = document.createRange();
        range.setStart(node, index);
        range.setEnd(node, Math.min(raw.length, index + text.length));
        const span = document.createElement("span");
        span.className = SENTENCE_CLASS;
        try {
          range.surroundContents(span);
          return span;
        } catch {
          return blockOf(node, this.root);
        }
      }
      node = walker.nextNode() as Text | null;
    }
    return null;
  }

  clear(): void {
    for (const marker of this.markers) {
      marker.el.classList.remove(marker.className, FLASH_CLASS);
      marker.badge?.remove();
    }
    this.markers = [];
    for (const wrapper of this.wrappers) {
      const parent = wrapper.parentNode;
      if (!parent) continue;
      while (wrapper.firstChild) parent.insertBefore(wrapper.firstChild, wrapper);
      parent.removeChild(wrapper);
    }
    this.wrappers = [];
    for (const cleanup of this.cleanups) cleanup();
    this.cleanups = [];
    if (this.root) {
      this.root.querySelectorAll<HTMLElement>("[data-rqg-badge]").forEach((node) => node.remove());
      this.root
        .querySelectorAll<HTMLElement>(`.${FLAG_CLASS},.${FOCUS_CLASS},.${SENTENCE_CLASS}`)
        .forEach((node) => node.classList.remove(FLAG_CLASS, FOCUS_CLASS, SENTENCE_CLASS, FLASH_CLASS));
    }
  }
}

export { FLAG_CLASS, FOCUS_CLASS, SENTENCE_CLASS, FLASH_CLASS };
