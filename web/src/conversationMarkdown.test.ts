import { describe, expect, it } from 'vitest'
import { renderConversationMarkdown } from './conversationMarkdown'

describe('untrusted conversation markdown', () => {
  it('renders headings, lists and code without enabling HTML or script links', () => {
    const html = renderConversationMarkdown('## 需求\n\n- **原图导出**\n\n`错误码`\n\n<script>alert(1)</script>\n\n[打开](javascript:alert(1))')
    expect(html).toContain('<h2>需求</h2>')
    expect(html).toContain('<strong>原图导出</strong>')
    expect(html).toContain('<code>错误码</code>')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('href="javascript:')
  })
  it('prevents automatic image requests and isolates external link navigation', () => {
    const html = renderConversationMarkdown('![说明](https://example.com/track?private=data)\n\n[官网](https://trailsnap.cn)')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('example.com')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).toContain('target="_blank"')
  })
})
