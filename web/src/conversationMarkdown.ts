import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true })
// Model output must never make automatic requests to model-selected image URLs.
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index]!.content)
markdown.renderer.rules.link_open = (tokens, index, options, _env, self) => {
  tokens[index]!.attrSet('target', '_blank')
  tokens[index]!.attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

export const renderConversationMarkdown = (text: string) => markdown.render(text)
