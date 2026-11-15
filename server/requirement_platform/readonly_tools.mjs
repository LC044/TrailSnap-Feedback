// Trusted, application-owned DSH plugin. No generic filesystem, shell or URL tools.
export const name = 'trailsnap-readonly-knowledge'
export const inject = ['tools']

export function apply(ctx, config) {
  const definitions = [
    ['read_trailsnap_source', 'Read TrailSnap release source. Supply query to find files by keywords or path fragments; alternatively supply an exact path and optional start_line to read 50 lines. Source includes Python, Vue/TypeScript, Rust and build/install scripts.',
      { query: { type: 'string', maxLength: 120 }, path: { type: 'string', maxLength: 500 }, start_line: { type: 'integer', minimum: 1 } }, []],
    ['search_official_docs', 'Read official TrailSnap documentation. Supply query to find pages; alternatively supply an exact returned path and optional start_line to read 50 lines.',
      { query: { type: 'string', maxLength: 120 }, path: { type: 'string', maxLength: 500 }, start_line: { type: 'integer', minimum: 1 } }, []],
  ]
  for (const [name, description, properties, required] of definitions) {
    ctx.tools.register({
      name, description,
      parameters: { type: 'object', properties, required, additionalProperties: false },
      output: { schema: { type: 'object' }, render(_args, value) { return [{ type: 'text', text: JSON.stringify(value) }] } },
      async execute(args) {
        const response = await fetch(config.endpoint + '/' + name, {
          method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + config.token },
          body: JSON.stringify(args), signal: AbortSignal.timeout(5000),
        })
        if (!response.ok) throw new Error('Readonly retrieval unavailable or limit reached')
        return response.json()
      },
    })
  }
}
