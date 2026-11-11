/** Presentation-only compatibility for older runs; original journal stays unchanged. */
export function publicAnswer(raw: string, kind: 'summary' | 'report' = 'summary'): string {
  let text = (raw || '').replace(/<(think|thinking|reasoning|analysis)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, '');
  const answers = [...text.matchAll(/<final_answer>([\s\S]*?)<\/final_answer>/gi)];
  if (answers.length) text = answers[answers.length - 1][1];
  else if (/<final_answer>/i.test(text)) return '';
  text = text.replace(/\[TOOL_CALL:[^\]]+\]/g, '').trim();
  if (text.startsWith('```markdown') && text.endsWith('```')) text = text.slice(11, -3).trim();
  if (kind === 'summary') {
    const headings = [...text.matchAll(/#{1,6}[ \t]+任务总结(?:[：:][^\n]*|[ \t]*)(?=\r?\n|$)/g)];
    if (headings.length) text = text.slice(headings[headings.length - 1].index);
  } else {
    const heading = /^#{1,2}[ \t]+[^\n]+/m.exec(text);
    if (heading) text = text.slice(heading.index);
  }
  if (/(?:I'll (?:start|read|analy[sz]e)|Let me (?:read|analy[sz]e|think)|I (?:need to|will) (?:read|analy[sz]e)|我(?:先|需要|将要)(?:读取|分析|思考)|现在(?:写入|读取)笔记|Note 已读取|"note_type"\s*:)/i.test(text)) return '';
  if (/^(?:报告生成失败|未获得有效研究资料)/.test(text)) return '';
  return text.trim();
}

/** Tool metadata remains inspectable; note bodies and reasoning are not UI content. */
export function toolMetadata(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(toolMetadata);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key]) => !/^(content|summary|reasoning(?:_content)?|thinking|thoughts?|analysis|raw_context|raw_content)$/i.test(key)).map(([key, item]) => [key, toolMetadata(item)]));
  if (typeof value === 'string') return publicAnswer(value);
  return value;
}
